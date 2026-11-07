#!/usr/bin/env python3
"""Commit guard.

Subcommands:
  pre-commit            scan the staged diff and run the repo's .claude/checks/
  commit-msg FILE       scan a commit message file
  pre-push [REMOTE URL] check commits being pushed (git pre-push stdin)
  claude-hook           Claude Code PreToolUse hook (tool input JSON on stdin)
  claude-post-hook      Claude Code PostToolUse hook: scan the commit the command just made
  install REPO          write pre-commit + commit-msg + pre-push hooks into one repo; copies this file to
                        <data dir>/guard.py and points the hooks there, so a plugin update cannot break them
                        (re-run install to refresh the copy)
  uninstall REPO        remove them again, restoring any hook they displaced

Code lives where this file lives (a plugin cache that is replaced on update). Mutable state lives in the data
dir, `$CLAUDE_CONFIG_DIR/commit-guard` or `~/.claude/commit-guard` (override: COMMIT_GUARD_DIR): config.json,
bypass.log, trusted-repos.txt, state/. Without a config.json the mode is warn.

Matched secret/PII values are never printed: findings are reported as
`file:line  rule-id` only. Heavy modules are imported lazily because the git
hooks run on every commit and interpreter start-up dominates the cost.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("COMMIT_GUARD_DIR")
                or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "commit-guard")
INSTALLED_GUARD = DATA_DIR / "guard.py"  # the copy that installed git hooks call
README_HINT = "the commit-guard README in the starter plugin (hooks/commit-guard/README.md)"
CONFIG_PATH = Path(os.environ.get("COMMIT_GUARD_CONFIG") or DATA_DIR / "config.json")
BYPASS_LOG = Path(os.environ.get("COMMIT_GUARD_BYPASS_LOG") or DATA_DIR / "bypass.log")
TRUSTED_PATH = Path(os.environ.get("COMMIT_GUARD_TRUSTED") or DATA_DIR / "trusted-repos.txt")
MAX_LISTED = 40
REPO_CHECK_TAIL = 20
REPO_CHECK_TIMEOUT = 120
GIT_BLOCK_EXIT = 17  # the installed hook script maps exactly this to a failing exit
CLAUDE_BLOCK_EXIT = 2
HOOK_MARKER = "# commit-guard-managed"
HOOK_NAMES = ("pre-commit", "commit-msg", "pre-push")
STATE_DIR = Path(os.environ.get("COMMIT_GUARD_STATE") or DATA_DIR / "state")
DEFAULT_PUSH_COMMITS = 1000
DEFAULT_RECORD_FROM = "2026-11-07T00:00:00+05:30"
ATTRIBUTION_ADVICE = ("Remove the Co-Authored-By/Generated-with lines - this user's commits are "
                      "attributed to the user only (house rule).")

# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

SECRET_RULES = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")),
    ("openai-key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{8,}")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY(?: BLOCK)?-----")),
    ("db-url-password", re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://[^\s:/@'\"]+:([^\s@/'\"]+)@")),
]
DB_PLACEHOLDER_PASSWORDS = {"pass", "password", "passwd", "pwd", "secret", "xxx", "xxxx", "changeme",
                            "your_password", "yourpassword", "password123", "example"}

# Indian mobile: an explicit +91 or 0 prefix, or a phone-ish keyword nearby.
MOBILE_RE = re.compile(r"(?<![\w.])(\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\w)")
PHONE_WORD_RE = re.compile(r"\b(?:phone|mobile|mob|call|whatsapp|contact|tel)", re.I)
ID_FIELD_RE = re.compile(r"(?:\bid|_id|id|size|count|bytes|timestamp|total|num)[\"']?\s*[:=]\s*[\"']?$", re.I)
# Aadhaar: first digit 2-9, 12 digits, valid Verhoeff checksum.
AADHAAR_RE = re.compile(r"(?<![\w.])[2-9]\d{3}\s?\d{4}\s?\d{4}(?![\w])")
# PAN: AAAAA9999A where the 4th letter is the holder type.
PAN_RE = re.compile(r"(?<!\w)[A-Z]{3}[PCHFATBLJG][A-Z]\d{4}[A-Z](?!\w)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
FILE_EXT_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "css", "js", "jsx", "ts", "tsx",
                 "json", "md", "py", "rs", "go", "txt", "html", "yml", "yaml", "map", "woff", "woff2"}
WARN_ONLY_RULES = {"email"}

ATTRIBUTION_RULES = [
    ("ai-coauthor", re.compile(r"Co-Authored-By:.*(Claude|anthropic)", re.I)),
    ("ai-noreply", re.compile(r"noreply@anthropic\.com", re.I)),
    ("ai-generated-with", re.compile(r"Generated with \[?Claude", re.I)),
]

_VD = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
       [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
       [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
       [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VP = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
       [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
       [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff_valid(digits: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VD[c][_VP[i % 8][int(ch)]]
    return c == 0


class Finding:
    def __init__(self, where: str, line: int | None, rule: str, path: str | None = None):
        self.where, self.line, self.rule = where, line, rule
        self.path = path or where  # what the allowlist globs match (where may carry a commit prefix)
        self.warn_only = rule in WARN_ONLY_RULES

    def key(self):
        return (self.where, self.line, self.rule)

    def render(self) -> str:
        loc = self.where if self.line is None else f"{self.where}:{self.line}"
        return f"{loc}  {self.rule}" + ("  (warn-only)" if self.warn_only else "")


class OwnEmails:
    """The repo's configured emails, fetched with one git call and only if needed."""

    def __init__(self, repo):
        self.repo, self._v = repo, None

    def get(self) -> set[str]:
        if self._v is None:
            self._v = set()
            if self.repo is not None:
                r = git(["config", "--get-all", "user.email"], self.repo)
                self._v = {x.strip().lower() for x in r.stdout.decode("utf-8", "replace").splitlines() if x.strip()}
        return self._v


def _email_allowed(addr: str, own: OwnEmails) -> bool:
    a = addr.lower()
    local, _, domain = a.rpartition("@")
    if local.startswith(("noreply", "no-reply")) or domain.endswith("noreply.github.com") or local == "git":
        return True
    if domain in ("example.com", "example.org", "example.net", "localhost") or domain.endswith(".example.com"):
        return True
    if domain.rsplit(".", 1)[-1] in FILE_EXT_TLDS:
        return True
    return a in own.get()


def _mobile_hit(text: str) -> bool:
    for m in MOBILE_RE.finditer(text):
        if m.group(1):
            return True
        window = text[max(0, m.start() - 20):m.end() + 20]
        if PHONE_WORD_RE.search(window) and not ID_FIELD_RE.search(text[:m.start()]):
            return True
    return False


def _aadhaar_hit(text: str) -> bool:
    return any(verhoeff_valid(re.sub(r"\s", "", m.group(0))) for m in AADHAAR_RE.finditer(text))


def scan_line(text: str, own: OwnEmails, pii: bool = True, email: bool = True) -> list[str]:
    """Return rule ids matched on one line. Never returns matched text."""
    hits: list[str] = []
    for rule, rx in SECRET_RULES:
        for m in rx.finditer(text):
            if rule == "db-url-password":
                pw = m.group(1).lower()
                if pw in DB_PLACEHOLDER_PASSWORDS or re.search(r"[<>{}*$%]", pw):
                    continue
            hits.append(rule)
            break
    if pii:
        if _mobile_hit(text):
            hits.append("in-mobile")
        if _aadhaar_hit(text):
            hits.append("aadhaar")
        if PAN_RE.search(text):
            hits.append("pan")
        if email and "@" in text and any(not _email_allowed(m.group(0), own) for m in EMAIL_RE.finditer(text)):
            hits.append("email")
    return hits


# --------------------------------------------------------------------------
# git helpers
# --------------------------------------------------------------------------

def git(args: list[str], cwd, input_bytes: bytes | None = None):
    import subprocess
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, input=input_bytes)


def repo_root(cwd) -> Path | None:
    try:
        r = git(["rev-parse", "--show-toplevel"], cwd)
    except (OSError, NotADirectoryError):
        return None
    if r.returncode != 0:
        return None
    return Path(r.stdout.decode("utf-8", "replace").strip())


def hook_root() -> Path | None:
    """Git runs hooks from the work-tree top level, so no git call is needed."""
    cwd = Path.cwd()
    return cwd if (cwd / ".git").exists() else repo_root(cwd)


HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_added(diff: str):
    """Yield (path, lineno, text) for added lines of a -U0 unified diff."""
    path = None
    old_left = new_left = 0
    lineno = 0
    for raw in diff.split("\n"):
        if old_left > 0 or new_left > 0:
            c = raw[:1]
            if c == "+":
                new_left -= 1
                if path:
                    yield path, lineno, raw[1:]
                lineno += 1
            elif c == "-":
                old_left -= 1
            elif c == "\\":
                pass
            else:
                old_left -= 1
                new_left -= 1
                lineno += 1
            continue
        if raw.startswith("diff --git "):
            path = None
        elif raw.startswith("+++ "):
            p = raw[4:].split("\t")[0]
            path = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
        elif raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            if m:
                old_left = int(m.group(1)) if m.group(1) is not None else 1
                lineno = int(m.group(2))
                new_left = int(m.group(3)) if m.group(3) is not None else 1


def diff_text(repo, against_head: bool = False) -> str:
    args = ["-c", "core.quotepath=off", "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv"]
    if against_head and git(["rev-parse", "--verify", "-q", "HEAD"], repo).returncode == 0:
        args.append("HEAD")
    else:
        args.append("--cached")
    return git(args, repo).stdout.decode("utf-8", "replace")


def scan_diff(repo, against_head: bool = False) -> list[Finding]:
    diff = diff_text(repo, against_head)
    if not diff:
        return []
    own = OwnEmails(repo)
    seen, out = set(), []
    for path, lineno, text in parse_added(diff):
        for rule in scan_line(text, own):
            f = Finding(path, lineno, rule)
            if f.key() not in seen:
                seen.add(f.key())
                out.append(f)
    return out


TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*[ \t]*:[ \t]*\S")
VERIFIED_RE = re.compile(r"^Verified:[ \t]*\S.*?[ \t]*->[ \t]*\S", re.I)
UNVERIFIED_RE = re.compile(r"^Unverified:[ \t]*\S", re.I)
EXEMPT_SUBJECT_RE = re.compile(r"^(?:Merge\b|fixup!|squash!|amend!|Revert\s+\")")
EXEMPT_BODY_RE = re.compile(r"^(?:This reverts commit [0-9a-f]{7,}|\(cherry picked from commit [0-9a-f]{7,}\))", re.M)
RECORD_ADVICE = (
    'commit-guard: every commit needs a record of what was run, as a trailer in the LAST paragraph of the message:\n'
    '    git commit -m "Fix retry loop" -m "Verified: pytest tests/ -> 152 passed"\n'
    '    git commit -m "Fix retry loop" -m "Unverified: reasoned about the retry path, nothing was run"\n'
    '  Verified needs "<what was run> -> <result>". In an editor, end the message with a blank line then that line. '
    'Merges, fixup!/squash!, reverts and cherry-picks are exempt. If already committed: git commit --amend.')


def _cfg() -> dict:
    import json
    try:
        c = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def parse_dt(v):
    """ISO-8601 string to an aware datetime (a naive one is taken as local time)."""
    from datetime import datetime
    if not isinstance(v, str):
        raise ValueError("expected an ISO-8601 date-time string")
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.astimezone()


def record_required() -> bool:
    v = _cfg().get("require_record", True)
    return v if isinstance(v, bool) else True


def record_cutoff():
    """Commits authored before this are not judged for the record. Author date survives rebase and filter-branch."""
    try:
        return parse_dt(_cfg().get("record_required_from") or DEFAULT_RECORD_FROM)
    except (ValueError, TypeError):
        return parse_dt(DEFAULT_RECORD_FROM)


def push_cap() -> int:
    v = _cfg().get("pre_push_max_commits")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else DEFAULT_PUSH_COMMITS


def _now_author():
    """Author date of the commit being made: git's GIT_AUTHOR_DATE if it set one, else now."""
    from datetime import datetime
    raw = os.environ.get("GIT_AUTHOR_DATE", "").strip()
    if raw:
        try:
            m = re.match(r"^@?(\d+)(?:\s+([+-])(\d\d)(\d\d))?$", raw)
            if m:
                from datetime import timedelta, timezone
                tz = timezone.utc
                if m.group(2):
                    off = timedelta(hours=int(m.group(3)), minutes=int(m.group(4)))
                    tz = timezone(off if m.group(2) == "+" else -off)
                return datetime.fromtimestamp(int(m.group(1)), tz)
            return parse_dt(raw)
        except (ValueError, OverflowError):
            pass
    return datetime.now().astimezone()


def has_record(text: str) -> bool:
    """True if a Verified:/Unverified: line sits in the message's trailer block (git interpret-trailers rules)."""
    if "erified" not in text:
        return False
    lines = [l.rstrip() for l in text.splitlines() if not l.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    k = len(lines)
    while k > 0 and lines[k - 1].strip():
        k -= 1
    para = lines[k:]
    if k == 0 or not para:  # a single paragraph is the subject, never a trailer block
        return False
    trailers = [l for l in para if TRAILER_LINE_RE.match(l)]
    cont = [l for l in para if l[:1] in " \t"]
    if len(trailers) + len(cont) != len(para) and len(trailers) * 4 < len(para):
        return False
    return any(VERIFIED_RE.match(l) or UNVERIFIED_RE.match(l) for l in trailers)


def record_exempt_text(text: str) -> bool:
    first = next((l for l in text.splitlines() if l.strip() and not l.startswith("#")), "")
    return bool(EXEMPT_SUBJECT_RE.match(first) or EXEMPT_BODY_RE.search(text))


def record_exempt_files(root) -> bool:
    """A merge, cherry-pick or revert is in progress."""
    if root is None:
        return False
    g = Path(root) / ".git"
    try:
        if g.is_file():
            g = Path(root) / g.read_text(encoding="utf-8").split(":", 1)[1].strip()
        return any((g / n).exists() for n in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"))
    except (OSError, IndexError):
        return False


def record_missing(text: str, root, author_dt=None) -> bool:
    if not record_required() or has_record(text) or record_exempt_text(text) or record_exempt_files(root):
        return False
    return (author_dt or _now_author()) >= record_cutoff()


def scan_message(text: str, repo, record: bool = False) -> list[Finding]:
    own = OwnEmails(repo)
    seen, out = set(), []
    if record and record_missing(text, repo):
        out.append(Finding("commit-message", None, "missing-verification-record"))
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        rules = [r for r, rx in ATTRIBUTION_RULES if rx.search(line)]
        rules += scan_line(line, own, pii=True, email=False)
        for rule in rules:
            f = Finding("commit-message", None, rule)
            if f.key() not in seen:
                seen.add(f.key())
                out.append(f)
    return out


# --------------------------------------------------------------------------
# allowlist, config, repo checks
# --------------------------------------------------------------------------

def load_allowlist(repo) -> list[tuple[str, str]]:
    p = Path(repo) / ".claude" / "checks" / "allowlist.txt"
    entries = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            glob, _, rule = line.rpartition(":")
            entries.append((glob.strip(), rule.strip()))
    except OSError:
        pass
    return entries


def apply_allowlist(findings: list[Finding], allow: list[tuple[str, str]]) -> list[Finding]:
    if not allow:
        return findings
    import fnmatch
    return [f for f in findings
            if not any(rule in ("*", f.rule) and fnmatch.fnmatch(f.path, glob) for glob, rule in allow)]


def load_mode() -> tuple[str, str]:
    """Return (mode, note); mode is 'warn', 'block' or 'error' (config invalid)."""
    import json
    from datetime import date
    if not CONFIG_PATH.exists():  # nothing configured: newcomers get warnings and opt in to blocking
        return "warn", ""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("config must be a JSON object")
        mode = cfg.get("mode", "warn")
        if mode not in ("warn", "block"):
            raise ValueError('"mode" must be "warn" or "block"')
        block_from = cfg.get("block_from")
        if block_from is not None and not isinstance(block_from, str):
            raise ValueError('"block_from" must be a YYYY-MM-DD string')
        due = date.fromisoformat(block_from) if block_from else None
        if cfg.get("record_required_from") is not None:
            parse_dt(cfg["record_required_from"])
        cap = cfg.get("pre_push_max_commits")
        if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap < 1):
            raise ValueError('"pre_push_max_commits" must be a positive integer')
        if mode == "block":
            return "block", ""
        if due and date.today() >= due:
            return "block", f"block_from {block_from} reached"
        return "warn", (f"blocks from {block_from}" if block_from else "")
    except (OSError, ValueError, TypeError, AttributeError) as e:
        return "error", f"config invalid ({type(e).__name__}: {e})"


def _norm(p) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


def repo_trusted(repo) -> bool:
    try:
        lines = TRUSTED_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    me = _norm(repo)
    return any(_norm(l.strip()) == me for l in lines if l.strip() and not l.startswith("#"))


def find_bash() -> str | None:
    """Git's bash, never the WSL launcher in System32."""
    import shutil
    import subprocess
    try:
        ep = subprocess.run(["git", "--exec-path"], capture_output=True, text=True).stdout.strip()
        root = Path(ep).parents[2]
        for rel in ("bin/bash.exe", "usr/bin/bash.exe"):
            if (root / rel).exists():
                return str(root / rel)
    except (OSError, IndexError):
        pass
    found = shutil.which("bash")
    return found if found and "system32" not in found.lower() else None


def run_repo_checks(repo) -> tuple[list[tuple[str, str]], str | None]:
    """Run scripts in <repo>/.claude/checks/ if the repo is trusted.

    Returns (failures, skipped_note). Third-party repos can ship arbitrary scripts there.
    """
    d = Path(repo) / ".claude" / "checks"
    if not d.is_dir():
        return [], None
    scripts = [s for s in sorted(d.iterdir()) if s.is_file() and s.suffix.lower() in (".sh", ".py", ".ps1")]
    if not scripts:
        return [], None
    if not repo_trusted(repo):
        return [], "commit-guard: repo checks skipped (repo not listed in trusted-repos.txt)"
    import shutil
    import subprocess
    failures = []
    for script in scripts:
        ext = script.suffix.lower()
        if ext == ".sh":
            bash = find_bash()
            # A repo-relative POSIX path: MSYS mangles absolute paths that contain an apostrophe.
            cmd = [bash, script.relative_to(Path(repo)).as_posix()] if bash else None
        elif ext == ".py":
            cmd = [sys.executable, str(script)]
        else:
            ps = shutil.which("powershell") or shutil.which("pwsh")
            cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)] if ps else None
        if cmd is None:
            failures.append((f"{script.name} (no interpreter found)", ""))
            continue
        try:
            r = subprocess.run(cmd, cwd=str(repo), capture_output=True, timeout=REPO_CHECK_TIMEOUT)
            code, out = r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            code, out = -1, f"timed out after {REPO_CHECK_TIMEOUT}s"
        except OSError as e:
            code, out = -1, str(e)
        if code != 0:
            failures.append((f"{script.name} (exit {code})", "\n".join(out.splitlines()[-REPO_CHECK_TAIL:])))
    return failures, None


# --------------------------------------------------------------------------
# reporting, bypass
# --------------------------------------------------------------------------

def report(findings: list[Finding], failures: list[tuple[str, str]], ctx: str, notes: list[str] | None = None) -> int:
    """ctx is 'git' or 'claude'. Returns the exit code for that caller."""
    notes = notes or []
    for n in notes:
        print(n, file=sys.stderr)
    if not findings and not failures:
        return 0
    blocking = [f for f in findings if not f.warn_only] + failures
    mode, note = load_mode()
    lines = [f"commit-guard: {len(findings) + len(failures)} problem(s) found"]
    for f in findings[:MAX_LISTED]:
        lines.append("  " + f.render())
    if len(findings) > MAX_LISTED:
        lines.append(f"  ... and {len(findings) - MAX_LISTED} more")
    for label, tail in failures:
        lines.append(f"  repo-check  {label}")
        lines.extend("    " + t for t in tail.splitlines())
    if any(f.rule.startswith("ai-") for f in findings):
        lines.append("commit-guard: " + ATTRIBUTION_ADVICE)
    if any(f.rule == "missing-verification-record" for f in findings):
        lines.append(RECORD_ADVICE)
    block_code = CLAUDE_BLOCK_EXIT if ctx == "claude" else GIT_BLOCK_EXIT
    if not blocking:
        lines.append("commit-guard: WARNING only (these rules never block), commit allowed.")
        code = 0
    elif mode == "block":
        lines.append("commit-guard: BLOCKED." + (f" ({note})" if note else "")
                     + " Values are deliberately not shown. Bypass is for the human only; see " + README_HINT + ".")
        code = block_code
    elif mode == "warn":
        lines.append("commit-guard: WARNING only, commit allowed" + (f" ({note})" if note else "") + ".")
        code = 0
    elif ctx == "claude":
        lines.append(f"commit-guard: guard error, fix config: {note}. Commit blocked until the config is valid.")
        code = block_code
    else:
        lines.append(f"commit-guard: {note}; fix config.json. Commit allowed (guard fails open for the human).")
        code = 0
    text = "\n".join(lines)
    print(text, file=sys.stderr)
    if ctx == "claude" and code == 0:
        # Exit-0 stderr never reaches the model; additionalContext does.
        import json
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}))
    return code


def bypass_requested() -> bool:
    return os.environ.get("COMMIT_GUARD_BYPASS", "") not in ("", "0")


def log_bypass(repo, hook: str) -> None:
    from datetime import datetime
    reason = os.environ.get("COMMIT_GUARD_REASON", "").replace("\n", " ").replace("\t", " ")
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')}\t{repo or os.getcwd()}\t{hook}\t{reason}\n"
    try:
        BYPASS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(BYPASS_LOG, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as e:
        print(f"commit-guard: could not write bypass log ({e})", file=sys.stderr)
    print("commit-guard: BYPASSED (logged)", file=sys.stderr)


# --------------------------------------------------------------------------
# git hook entry points
# --------------------------------------------------------------------------

def cmd_pre_commit() -> int:
    repo = hook_root()
    if repo is None:
        return 0
    if bypass_requested():
        log_bypass(repo, "pre-commit")
        return 0
    findings = scan_diff(repo)
    if findings:
        findings = apply_allowlist(findings, load_allowlist(repo))
    failures, note = run_repo_checks(repo)
    return report(findings, failures, "git", [note] if note else None)


def cmd_commit_msg(path: str) -> int:
    if bypass_requested():
        log_bypass(hook_root(), "commit-msg")
        return 0
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    repo = hook_root()
    findings = scan_message(text, None, record=False)  # emails are not scanned in messages: no repo lookup
    if record_missing(text, repo):
        findings.insert(0, Finding("commit-message", None, "missing-verification-record"))
    if findings and repo:
        findings = apply_allowlist(findings, load_allowlist(repo))
    return report(findings, [], "git")


def scan_commits(repo, revargs: list[str], limit: int | None = None):
    """Scan the commits selected by revargs.

    Returns (findings, skipped) or None if git failed. Secrets are scanned on every commit; the record rule
    only on commits authored on or after record_required_from. `skipped` counts commits beyond the cap.
    """
    limit = limit or push_cap()
    r = git(["log", *revargs, f"-n{limit + 1}", "-p", "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
             "--format=%x1e%H%x1f%P%x1f%aI%x1f%B%x1d"], repo)
    if r.returncode != 0:
        return None
    records = r.stdout.decode("utf-8", "replace").split("\x1e")[1:]
    skipped = 0
    if len(records) > limit:
        c = git(["rev-list", "--count", *[a for a in revargs if not a.startswith("-n")]], repo)
        total = int(c.stdout.strip() or 0) if c.returncode == 0 and c.stdout.strip().isdigit() else limit + 1
        skipped = max(1, total - limit)
        records = records[:limit]
    own, out, seen = OwnEmails(repo), [], set()
    cutoff = record_cutoff()
    for rec in records:
        head, _, diff = rec.partition("\x1d")
        sha, parents, authored, body = (head.split("\x1f", 3) + ["", "", ""])[:4]
        sha7 = sha[:7]
        try:
            old = parse_dt(authored) < cutoff
        except ValueError:
            old = False
        if len(parents.split()) < 2 and not old and record_missing_msg(body):
            out.append(Finding(f"commit {sha7}", None, "missing-verification-record", path="commit-message"))
        for path, lineno, text in parse_added(diff):
            for rule in scan_line(text, own, pii=False):
                f = Finding(f"{sha7}:{path}", lineno, rule, path=path)
                if f.key() not in seen:
                    seen.add(f.key())
                    out.append(f)
    return out, skipped


def record_missing_msg(body: str) -> bool:
    """For an already-made commit: no in-progress files to consult, only the message."""
    return record_required() and not has_record(body) and not record_exempt_text(body)


def cmd_pre_push(args: list[str]) -> int:
    repo = hook_root()
    if repo is None:
        return 0
    if bypass_requested():
        log_bypass(repo, "pre-push")
        return 0
    findings: list[Finding] = []
    seen = set()
    skipped_total = 0
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        lsha, rsha = parts[1], parts[3]
        if set(lsha) == {"0"}:  # deleting a ref
            continue
        res = None if set(rsha) == {"0"} else scan_commits(repo, [f"{rsha}..{lsha}"])
        if res is None:  # new branch, or the remote sha is not known locally
            res = scan_commits(repo, [lsha, "--not", "--remotes"]) or ([], 0)
        found, skipped = res
        skipped_total += skipped
        for f in found:
            if f.key() not in seen:
                seen.add(f.key())
                findings.append(f)
    findings = apply_allowlist(findings, load_allowlist(repo))
    notes = [f"commit-guard: {skipped_total} commit(s) were not scanned (over pre_push_max_commits={push_cap()})"] \
        if skipped_total else None
    return report(findings, [], "git", notes)

# --------------------------------------------------------------------------
# install / uninstall (per repo, opt-in)
# --------------------------------------------------------------------------

def _write_lf(path, text: str) -> None:
    """Write text with LF line endings. Path.write_text(newline=) needs Python 3.10."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def hook_script(name: str) -> str:
    guard = INSTALLED_GUARD.as_posix()
    if name == "pre-push":
        return f"""#!/bin/sh
{HOOK_MARKER} (python guard.py uninstall <repo> removes this)
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp)" || exit 0
trap 'rm -f "$tmp"' EXIT
cat > "$tmp"
if [ -f "$here/pre-push.local" ]; then
  "$here/pre-push.local" "$@" < "$tmp" || exit $?
fi
py="$(command -v python || command -v python3)"
if [ -z "$py" ]; then echo "commit-guard: python not found, guard skipped" >&2; exit 0; fi
"$py" -S "{guard}" pre-push "$@" < "$tmp"
rc=$?
case $rc in
  0) exit 0 ;;
  {GIT_BLOCK_EXIT}) exit 1 ;;
  *) echo "commit-guard: guard error (python exit $rc), guard skipped" >&2; exit 0 ;;
esac
"""
    arg = ' "$1"' if name == "commit-msg" else ""
    return f"""#!/bin/sh
{HOOK_MARKER} (python guard.py uninstall <repo> removes this)
here="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$here/{name}.local" ]; then
  "$here/{name}.local" "$@" || exit $?
fi
py="$(command -v python || command -v python3)"
if [ -z "$py" ]; then echo "commit-guard: python not found, guard skipped" >&2; exit 0; fi
"$py" -S "{guard}" {name}{arg}
rc=$?
case $rc in
  0) exit 0 ;;
  {GIT_BLOCK_EXIT}) exit 1 ;;
  *) echo "commit-guard: guard error (python exit $rc), guard skipped" >&2; exit 0 ;;
esac
"""


def _hooks_dir(repo: Path) -> Path:
    r = git(["rev-parse", "--git-path", "hooks"], repo)
    p = Path(r.stdout.decode("utf-8", "replace").strip())
    return p if p.is_absolute() else (repo / p)


def _inside(child: Path, parent: Path) -> bool:
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p + os.sep)


def cmd_install(path: str, uninstall: bool = False) -> int:
    repo = repo_root(path)
    if repo is None:
        print(f"commit-guard: {path} is not a git repository", file=sys.stderr)
        return 1
    hooks = _hooks_dir(repo)
    gitdir = Path(git(["rev-parse", "--git-common-dir"], repo).stdout.decode().strip())
    gitdir = gitdir if gitdir.is_absolute() else repo / gitdir
    if not (_inside(hooks, repo) or _inside(hooks, gitdir)):
        print(f"commit-guard: hooks dir {hooks} is shared and outside this repo; refusing to write there",
              file=sys.stderr)
        return 1
    if uninstall:
        for name in HOOK_NAMES:
            t, local = hooks / name, hooks / f"{name}.local"
            if t.exists() and HOOK_MARKER in t.read_text(encoding="utf-8", errors="replace"):
                t.unlink()
                if local.exists():
                    local.rename(t)
                print(f"removed {t}" + (" (restored previous hook)" if t.exists() else ""))
            else:
                print(f"skipped {t} (not a commit-guard hook)")
        return 0
    plan = []
    for name in HOOK_NAMES:
        t, local = hooks / name, hooks / f"{name}.local"
        ours = t.exists() and HOOK_MARKER in t.read_text(encoding="utf-8", errors="replace")
        if t.exists() and not ours and local.exists():
            print(f"commit-guard: both {t} and {local} exist; resolve by hand. Nothing written.", file=sys.stderr)
            return 1
        plan.append((name, t, local, t.exists() and not ours))
    hooks.mkdir(parents=True, exist_ok=True)
    try:
        INSTALLED_GUARD.parent.mkdir(parents=True, exist_ok=True)
        if not (INSTALLED_GUARD.exists() and INSTALLED_GUARD.samefile(CODE_DIR / "guard.py")):
            import shutil
            shutil.copyfile(CODE_DIR / "guard.py", INSTALLED_GUARD)
        print(f"copied guard.py to {INSTALLED_GUARD} (re-run install after a plugin update to refresh it)")
    except OSError as e:
        print(f"commit-guard: could not copy guard.py to {INSTALLED_GUARD} ({e}). Nothing written.", file=sys.stderr)
        return 1
    for name, t, local, displace in plan:
        if displace:
            t.rename(local)
        _write_lf(t, hook_script(name))
        t.chmod(t.stat().st_mode | 0o111)
        print(f"installed {t}" + (f" (previous hook kept as {local.name} and chained)" if displace else ""))
    return 0


# --------------------------------------------------------------------------
# Claude Code PreToolUse hook: deciding whether the command really commits
# --------------------------------------------------------------------------

GIT_COMMIT_RE = re.compile(
    r"(?<![\w-])git(?:\.exe)?(?:\s+(?:-C\s+(?:\"[^\"]*\"|'[^']*'|\S+)|-c\s+\S+|--[\w-]+(?:=\S+)?))*\s+commit(?![\w-])")
HEREDOC_RE = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2)([^\n]*)\n(.*?)\n[ \t]*\3[ \t]*(?=\n|$)", re.S)
PS_HERESTRING_RE = re.compile(r"@(['\"]).*?\1@", re.S)
SHELLS = {"bash", "sh", "zsh", "dash", "ash", "powershell", "pwsh", "cmd", "eval"}
WRAPPERS = {"env", "time", "sudo", "command", "nohup", "exec", "call"}
KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "{"}
CD_WORDS = {"cd", "pushd", "set-location", "sl", "chdir"}
ARG_SHORT = set("mFCctSu")
GIT_OPTS_WITH_VALUE = {"--git-dir", "--work-tree", "--namespace", "--config-env"}


def _word(tok: str) -> str:
    base = tok.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def _unq(t: str) -> str:
    return t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"" else t


def live_text(cmd: str) -> str:
    """Drop text that is only data: heredoc bodies and PowerShell here-strings.

    A heredoc whose line feeds a shell interpreter is code, so it stays.
    """
    def heredoc(m: re.Match) -> str:
        start = cmd.rfind("\n", 0, m.start()) + 1
        words = {_word(w) for w in (cmd[start:m.start()] + " " + m.group(4)).split()}
        return m.group(0) if words & SHELLS else m.group(1) + m.group(4) + "\n"
    return PS_HERESTRING_RE.sub(" ", HEREDOC_RE.sub(heredoc, cmd))


def tokenize(text: str) -> list[str | None]:
    """Shell-ish tokens; None marks a command separator. Quotes stay on the token."""
    toks: list[str | None] = []
    cur: list[str] = []
    q = None
    i, n = 0, len(text)

    def flush(sep=False):
        if cur:
            toks.append("".join(cur))
            cur.clear()
        if sep:
            toks.append(None)

    while i < n:
        c = text[i]
        if q:
            cur.append(c)
            if q == '"' and c in "\\`" and i + 1 < n:
                cur.append(text[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"":
            q = c
            cur.append(c)
        elif c in " \t\r":
            flush()
        elif c in ";&|()\n":
            flush(True)
        else:
            cur.append(c)
        i += 1
    if q:
        raise ValueError("unterminated quote")
    flush()
    return toks


def find_commits(cmd: str, depth: int = 0) -> list[dict]:
    """Every real `git [opts] commit` invocation in cmd. Mentions in data do not count.

    Each dict: C (-C values), c (-c values), args (tokens after `commit`), cds (cd targets before it),
    adds (earlier `git add` invocations), prefix (env/option tokens that could bypass the guard).
    """
    live = live_text(cmd)
    try:
        toks = tokenize(live)
    except ValueError:
        m = GIT_COMMIT_RE.search(live)
        if not m:
            return []
        tail = live[m.end():].split("\n", 1)[0].split()
        adds = [{"C": [], "args": ["."], "cds": []}] if re.search(r"\bgit\b[^\n]*\badd\b", live) else []
        return [{"C": [], "c": [], "args": tail, "cds": [], "adds": adds, "prefix": live[:m.end()], "fallback": True}]
    out: list[dict] = []
    state = {"cds": [], "adds": [], "envs": []}
    seg: list[str] = []
    for t in toks + [None]:
        if t is not None:
            seg.append(t)
            continue
        if seg:
            _scan_segment(seg, state, out, depth)
        seg = []
    return out


ENV_WORDS = {"export", "set", "setx", "env", "declare", "typeset", "set-item", "new-item", "setenv"}


def _is_env_segment(seg: list[str]) -> bool:
    first = seg[0]
    return bool(re.match(r"^[A-Za-z_]\w*=", first) or _word(first) in ENV_WORDS
                or first.lower().startswith(("$env:", "[environment]", "env:")) or "COMMIT_GUARD" in first)


def _scan_segment(seg: list[str], state: dict, out: list[dict], depth: int) -> None:
    cds, adds, envs = state["cds"], state["adds"], state["envs"]
    if _is_env_segment(seg):
        envs.append(" ".join(seg))
    i = 0
    while i < len(seg):
        t = seg[i]
        if re.match(r"^[A-Za-z_]\w*=", t) or _word(t) in WRAPPERS or t in KEYWORDS or (i > 0 and t.startswith("-")):
            i += 1
            continue
        break
    if i >= len(seg):
        return
    w = _word(seg[i])
    if w in CD_WORDS:
        rest = [x for x in seg[i + 1:] if x.lower() not in ("/d", "-l", "-p", "--") and not x.startswith("-")]
        if rest:
            cds.append(_unq(rest[0]))
    elif w == "git":
        j, Cs, cs = i + 1, [], []
        while j < len(seg):
            u = _unq(seg[j])
            if u == "-C" and j + 1 < len(seg):
                Cs.append(_unq(seg[j + 1])); j += 2
            elif u == "-c" and j + 1 < len(seg):
                cs.append(_unq(seg[j + 1])); j += 2
            elif u in GIT_OPTS_WITH_VALUE:
                j += 2
            elif u.startswith("-"):
                j += 1
            else:
                break
        sub = _unq(seg[j]) if j < len(seg) else ""
        if sub == "commit":
            out.append({"C": Cs, "c": cs, "args": seg[j + 1:], "cds": list(cds), "adds": list(adds),
                        "prefix": " ".join(envs + seg[:j + 1])})
        elif sub in ("add", "stage"):
            adds.append({"C": Cs, "args": seg[j + 1:], "cds": list(cds)})
        elif sub == "config" and any("hookspath" in x.lower() for x in seg[j + 1:]):
            envs.append(" ".join(seg))
    elif w in SHELLS and depth < 3:
        for x in seg[i + 1:]:
            u = _unq(x)
            if "git" in u and "commit" in u:
                for c in find_commits(u, depth + 1):
                    c["cds"] = list(cds) + c["cds"]
                    c["adds"] = list(adds) + c["adds"]
                    c["prefix"] = " ".join(envs + seg[:i]) + " " + c["prefix"]
                    out.append(c)


def commit_flags(commits: list[dict]) -> dict:
    out = {"no_verify": False, "all": False, "files": [], "paths": [], "messages": [], "reuse": [], "trailers": []}
    for c in commits:
        toks = [_unq(t) for t in c["args"]]
        i = 0
        while i < len(toks):
            t = toks[i]
            if t == "--no-verify":
                out["no_verify"] = True
            elif t == "--all":
                out["all"] = True
            elif t.startswith("--file="):
                out["files"].append(t[7:])
            elif t.startswith("--trailer="):
                out["trailers"].append(t[10:])
            elif t == "--trailer" and i + 1 < len(toks):
                out["trailers"].append(toks[i + 1]); i += 1
            elif t.startswith("--message="):
                out["messages"].append(t[10:])
            elif t.startswith(("--reuse-message=", "--reedit-message=")):
                out["reuse"].append(t.split("=", 1)[1])
            elif t in ("--message", "--reuse-message", "--reedit-message") and i + 1 < len(toks):
                out["messages" if t == "--message" else "reuse"].append(toks[i + 1]); i += 1
            elif t == "--file" and i + 1 < len(toks):
                out["files"].append(toks[i + 1]); i += 1
            elif t in ("--message", "--reuse-message", "--reedit-message", "--template", "--author", "--date"):
                i += 1
            elif t == "--":
                out["paths"].extend(toks[i + 1:])
                break
            elif t.startswith("--"):
                pass
            elif not t.startswith("-") or t == "-":
                out["paths"].append(t)
            elif t.startswith("-") and len(t) > 1:
                for j, ch in enumerate(t[1:]):
                    if ch == "n":
                        out["no_verify"] = True
                    elif ch == "a":
                        out["all"] = True
                    if ch in ARG_SHORT:
                        val = t[2 + j:] or (toks[i + 1] if i + 1 < len(toks) else "")
                        if val and ch == "F":
                            out["files"].append(val)
                        elif val and ch == "m":
                            out["messages"].append(val)
                        elif val and ch in "Cc":
                            out["reuse"].append(val)
                        if ch in "mFCct" and not t[2 + j:]:
                            i += 1
                        break
            i += 1
    return out


def _to_native(p: str) -> str:
    m = re.match(r"^/([a-zA-Z])/(.*)$", p)
    return f"{m.group(1).upper()}:/{m.group(2)}" if m and os.name == "nt" else p


def resolve_cwd(base: str, commit: dict) -> str:
    cur = base
    for p in commit["cds"] + commit["C"]:
        cur = os.path.join(cur, _to_native(p))
    return cur


def agent_bypass_reason(commits: list[dict]) -> str | None:
    """Only the commit's own env prefix and options count, not other segments of the command."""
    for c in commits:
        if "COMMIT_GUARD" in c["prefix"]:
            return "COMMIT_GUARD*"
        if "hookspath" in c["prefix"].lower():
            return "core.hooksPath"
    if commit_flags(commits)["no_verify"]:
        return "--no-verify / -n"
    return None


def parse_add(args: list[str]) -> tuple[list[str], bool, bool] | None:
    """(pathspecs, tracked_only, force) for `git add` args, or None if nothing would be staged."""
    toks = [_unq(t) for t in args]
    paths, all_, update, force, rest = [], False, False, False, False
    for t in toks:
        if rest or not t.startswith("-") or t == "-":
            paths.append(t)
        elif t == "--":
            rest = True
        elif t.startswith("--"):
            all_ |= t == "--all"
            update |= t == "--update"
            force |= t == "--force"
        else:
            all_ |= "A" in t
            update |= "u" in t
            force |= "f" in t
    if not paths and (all_ or update):
        paths = ["."]
    if not paths:
        return None
    paths = ["." if re.search(r"[$`]", p) else p for p in paths]  # unresolvable: be conservative
    return paths, update and not all_, force


def scan_pending(cwd: str, paths: list[str], tracked_only: bool, force: bool) -> list[Finding]:
    """Findings in what `git add <paths>` would stage: working-tree changes vs HEAD plus untracked files."""
    repo = repo_root(cwd)
    if repo is None:
        return []
    own, out, seen = OwnEmails(repo), [], set()

    def add(path, lineno, text):
        for rule in scan_line(text, own):
            f = Finding(path, lineno, rule)
            if f.key() not in seen:
                seen.add(f.key())
                out.append(f)

    base = ["-c", "core.quotepath=off", "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv"]
    if git(["rev-parse", "--verify", "-q", "HEAD"], cwd).returncode == 0:
        base.append("HEAD")
    diff = git([*base, "--", *paths], cwd).stdout.decode("utf-8", "replace")
    for path, lineno, text in parse_added(diff):
        add(path, lineno, text)
    if not tracked_only:
        args = ["ls-files", "--others", "-z"] + ([] if force else ["--exclude-standard"]) + ["--", *paths]
        for rel in git(args, cwd).stdout.decode("utf-8", "replace").split("\0"):
            full = Path(cwd) / rel
            if not rel or not full.is_file() or full.stat().st_size > 2_000_000:
                continue
            data = full.read_bytes()
            if b"\0" in data[:8192]:
                continue
            label = os.path.relpath(full, repo).replace("\\", "/")
            for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                add(label, n, line)
    return out


def commit_message_text(cmd: str, commits: list[dict], flags: dict, cwd: str) -> str:
    """The message git would record: -m values, -F file, -C/-c reuse. Empty when the editor would open."""
    if any(c.get("fallback") for c in commits):  # could not parse the command: scan all of it
        return cmd
    bodies: dict[str, list[str]] = {}
    for m in HEREDOC_RE.finditer(cmd):
        bodies.setdefault(m.group(3), []).append(m.group(5))

    def fill(m: re.Match) -> str:
        lst = bodies.get(m.group(2))
        return lst.pop(0) if lst else ""

    def expand(v: str) -> str:
        # `$(cat <<'EOF' ... EOF)` is the message itself; any other heredoc marker is replaced by its body.
        v = re.sub(r"\$\(\s*cat\s+<<-?\s*(['\"]?)(\w+)\1\s*\)", lambda m: fill(m).strip("\n"), v)
        return re.sub(r"<<-?\s*(['\"]?)(\w+)\1", fill, v)

    parts = [expand(v) for v in flags["messages"]]
    for f in flags["files"]:
        if f == "-":  # `git commit -F - <<EOF`: the heredoc is the message
            parts.extend(b for lst in bodies.values() for b in lst)
            continue
        try:
            parts.append(Path(os.path.join(cwd, _to_native(f))).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    for rev in flags["reuse"]:
        if rev and not rev.startswith("-"):
            r = git(["log", "-1", "--format=%B", rev, "--"], cwd)
            if r.returncode == 0:
                parts.append(r.stdout.decode("utf-8", "replace"))
    if flags["trailers"]:
        parts.append("\n".join(flags["trailers"]))
    return "\n\n".join(parts)


def scan_command_secrets(commits: list[dict], repo, skip_rules: set[str]) -> list[Finding]:
    """Secret rules over the commit invocation's own env prefix and arguments, not chained segments."""
    own, out, seen = OwnEmails(repo), [], set()
    for c in commits:
        for text in [c["prefix"], *c["args"]]:
            for rule in scan_line(text, own, pii=False):
                if rule not in skip_rules and rule not in seen:
                    seen.add(rule)
                    out.append(Finding("commit-command", None, rule))
    return out


def _head(repo) -> str:
    r = git(["rev-parse", "--verify", "-q", "HEAD"], repo)
    return r.stdout.decode().strip() if r.returncode == 0 else ""


def _state_file(tool_use_id) -> Path | None:
    tid = re.sub(r"[^A-Za-z0-9_-]", "", str(tool_use_id or ""))
    return STATE_DIR / f"{tid}.head" if tid else None


def _save_state(tool_use_id, repo) -> None:
    """Remember HEAD and the wall-clock start before the command runs, for the post hook."""
    import time
    f = _state_file(tool_use_id)
    if f is None:
        return
    try:
        now = time.time()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        for old in STATE_DIR.glob("*.head"):
            if now - old.stat().st_mtime > 86400:
                old.unlink()
        f.write_text(f"{repo or ''}\n{_head(repo) if repo else ''}\n{now!r}\n", encoding="utf-8")
    except OSError:
        pass


_isjunction = getattr(os.path, "isjunction", lambda p: False)  # os.path.isjunction needs Python 3.12
SKIP_HOME_DIRS = {"appdata", "application data", "local settings", "node_modules", "nethood", "printhood",
                  "recent", "sendto", "start menu", "templates", "cookies", "my documents", "music", "videos",
                  "pictures", "downloads", "onedrive", "3d objects", "contacts", "favorites", "links",
                  "saved games", "searches"}
MAX_DIR_ENTRIES = 300


def _git_dir_of(dotgit: Path) -> Path | None:
    try:
        if dotgit.is_dir():
            return dotgit
        if dotgit.is_file():
            line = dotgit.read_text(encoding="utf-8", errors="replace").strip()
            if line.startswith("gitdir:"):
                p = Path(line[7:].strip())
                return p if p.is_absolute() else (dotgit.parent / p).resolve()
    except OSError:
        pass
    return None


def _walk_up_to_repo(p: Path) -> Path | None:
    p = p if p.is_dir() else p.parent
    for cand in [p, *list(p.parents)[:8]]:
        if (cand / ".git").exists():
            return cand
    return None


def discover_repos(since: float, home: Path, explicit: list[Path]) -> dict[str, tuple[Path, Path]]:
    """Repos that may have committed since `since`: the explicit ones, plus every repo and worktree up to two
    levels under home whose HEAD reflog was modified at or after `since`. One stat per directory."""
    found: dict[str, tuple[Path, Path]] = {}

    def consider(root: Path, force: bool) -> None:
        gd = _git_dir_of(root / ".git")
        if gd is None:
            return
        try:
            if not force and (gd / "logs" / "HEAD").stat().st_mtime < since - 2:
                return
        except OSError:
            return
        found.setdefault(os.path.normcase(os.path.realpath(root)), (root, gd))

    for e in explicit:
        consider(e, True)

    def listing(path):
        import itertools
        try:
            with os.scandir(path) as it:
                return list(itertools.islice(it, MAX_DIR_ENTRIES))
        except OSError:
            return []

    def plain_dir(e) -> bool:
        return (e.is_dir(follow_symlinks=False) and not e.name.startswith(".")
                and e.name.lower() not in SKIP_HOME_DIRS and not _isjunction(e.path))

    for e1 in listing(home):
        if not plain_dir(e1):
            continue
        consider(Path(e1.path), False)
        for e2 in listing(e1.path):
            if e2.is_dir(follow_symlinks=False) and not e2.name.startswith(".") and not _isjunction(e2.path):
                consider(Path(e2.path), False)
    return found


COMMIT_REFLOG_RE = re.compile(r"^commit(?: \((?:amend|initial|merge)\))?:")


def reflog_commits_since(gitdir: Path, since: float) -> list[str]:
    """Shas HEAD's reflog recorded as commits (not resets, pulls or rebases) at or after `since`."""
    try:
        with open(gitdir / "logs" / "HEAD", "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 262144))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    shas: list[str] = []
    for line in lines:
        head, _, msg = line.partition("\t")
        if not COMMIT_REFLOG_RE.match(msg) or ">" not in head:
            continue
        try:
            when = int(head.rsplit(">", 1)[1].split()[0])
        except (ValueError, IndexError):
            continue
        sha = head.split()[1] if len(head.split()) > 1 else ""
        if when >= int(since) and sha and sha not in shas:
            shas.append(sha)
    return shas


def _literal_repos(cmd: str, base: str) -> list[Path]:
    """Repo paths written literally in the command (cd ~/x, git -C /path, ...)."""
    out: list[Path] = []
    try:
        toks = [t for t in tokenize(live_text(cmd)) if t]
    except ValueError:
        return out
    for t in toks:
        u = _unq(t)
        if "$" in u or not re.search(r"[/\\~]", u):
            continue
        p = Path(os.path.expanduser(_to_native(u)))
        p = p if p.is_absolute() else Path(base) / p
        try:
            root = _walk_up_to_repo(p) if p.exists() else None
        except OSError:
            root = None
        if root is not None and root not in out:
            out.append(root)
    return out


POST_ADVICE_SECRET = ("A secret is in the commit: remove it from the file, then fix with `git commit --amend`. "
                      "If it was a real credential, rotate it (it stays in the object database and reflog).")
POST_ADVICE_FIX = ("Fix with `git commit --amend` BEFORE pushing; do not push until this is clean. "
                   "This hook never rewrites commits for you. Values are deliberately not shown.")


def _post_context(findings: list[Finding]) -> str:
    lines = [f"commit-guard (post-commit): the commit(s) you just made have {len(findings)} problem(s)"]
    lines += ["  " + f.render() for f in findings[:MAX_LISTED]]
    if any(f.rule == "missing-verification-record" for f in findings):
        lines.append(RECORD_ADVICE)
    if any(f.rule != "missing-verification-record" for f in findings):
        lines.append(POST_ADVICE_SECRET)
    lines.append(POST_ADVICE_FIX)
    return "\n".join(lines)


def cmd_claude_post_hook(stdin_text: str) -> int:
    """PostToolUse: after a real git commit, scan the commits it made and tell the agent what to fix.

    Which repos and commits is decided from reflog evidence (commit entries since the command started), not by
    parsing the command, so `cd "$VAR"`, `git -C "$VAR"` and commits inside loops are covered.
    Never rewrites anything and never blocks; the commits already exist.
    """
    import json
    try:
        data = json.loads(stdin_text)
    except ValueError:
        return 0
    cmd = ((data.get("tool_input") or {}).get("command")) or ""
    if not isinstance(cmd, str) or "commit" not in cmd:
        return 0
    commits = find_commits(cmd)
    if not commits:
        return 0
    base = data.get("cwd") or os.getcwd()
    cwd_repo = repo_root(resolve_cwd(base, commits[0]))
    before, start, f = None, None, _state_file(data.get("tool_use_id"))
    if f is not None and f.exists():
        try:
            saved = f.read_text(encoding="utf-8").splitlines()
            before = saved[1] if len(saved) > 1 else ""
            start = float(saved[2]) if len(saved) > 2 else None
            f.unlink()
        except (OSError, ValueError):
            pass
    findings: list[Finding] = []
    if start is not None:
        home = Path(os.environ.get("COMMIT_GUARD_HOME") or Path.home())
        explicit = ([cwd_repo] if cwd_repo else []) + _literal_repos(cmd, base)
        for root, gd in discover_repos(start, home, explicit).values():
            shas = reflog_commits_since(gd, start)
            res = scan_commits(root, ["--no-walk=unsorted", *shas], limit=len(shas)) if shas else None
            if not res:
                continue
            found = apply_allowlist(res[0], load_allowlist(root))
            if cwd_repo is None or _norm(root) != _norm(cwd_repo):
                for x in found:
                    x.where = f"[{Path(root).name}] {x.where}"
            findings += found
    elif cwd_repo is not None:  # no pre-hook state: all we have is HEAD
        head = _head(cwd_repo)
        if head and before != head:
            revargs = [f"{before}..{head}"] if before else [head, "-n1"] if before is None else [head]
            res = scan_commits(cwd_repo, revargs, limit=20 if before is not None else 1)
            findings = apply_allowlist(res[0] if res else [], load_allowlist(cwd_repo))
    if not findings:
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": _post_context(findings)}}))
    return 0


def cmd_claude_hook(stdin_text: str) -> int:
    import json
    from datetime import datetime
    try:
        data = json.loads(stdin_text)
    except ValueError:
        return 0
    cmd = ((data.get("tool_input") or {}).get("command")) or ""
    if not isinstance(cmd, str) or "commit" not in cmd:
        return 0
    commits = find_commits(cmd)
    if not commits:
        return 0
    why = agent_bypass_reason(commits)
    if why:
        print(f"commit-guard: blocked. Agents may not bypass the commit guard ({why} in a git commit command). "
              "Fix the reported problem or ask the user.", file=sys.stderr)
        return CLAUDE_BLOCK_EXIT
    cwd = resolve_cwd(data.get("cwd") or os.getcwd(), commits[0])
    repo = repo_root(cwd)
    _save_state(data.get("tool_use_id"), repo)  # even when the repo is unresolvable: the post hook needs the start time
    if repo is None:
        return 0
    flags = commit_flags(commits)
    message = commit_message_text(cmd, commits, flags, cwd)
    # Only a message we can actually read is checked for the record; the editor case is the commit-msg hook's.
    readable = not any(c.get("fallback") for c in commits) and bool(message.strip())
    msg_findings = scan_message(message, repo)
    if readable and record_missing(message, repo, datetime.now().astimezone()):
        msg_findings.insert(0, Finding("commit-message", None, "missing-verification-record"))
    findings = (scan_diff(repo, against_head=flags["all"]) + msg_findings
                + scan_command_secrets(commits, repo, {f.rule for f in msg_findings}))
    # `git add k && git commit` runs the add after this hook fires, so scan what will be staged.
    base_cwd = data.get("cwd") or os.getcwd()
    specs = [(resolve_cwd(base_cwd, a), parse_add(a["args"])) for c in commits for a in c["adds"]]
    specs = [(acwd, p) for acwd, p in specs if p]
    if flags["paths"]:
        specs.append((cwd, (flags["paths"], True, False)))
    done = set()
    for acwd, (paths, tracked_only, force) in specs:
        key = (acwd, tuple(paths), tracked_only, force)
        if key not in done:
            done.add(key)
            findings += scan_pending(acwd, paths, tracked_only, force)
    seen, unique = set(), []
    for f in findings:
        if f.key() not in seen:
            seen.add(f.key())
            unique.append(f)
    findings = unique
    findings = apply_allowlist(findings, load_allowlist(repo))
    failures, note = run_repo_checks(repo)
    return report(findings, failures, "claude", [note] if note else None)


# --------------------------------------------------------------------------

def _where(e: BaseException) -> str:
    import traceback
    tb = traceback.extract_tb(e.__traceback__)
    return f"{type(e).__name__} at {Path(tb[-1].filename).name}:{tb[-1].lineno}" if tb else type(e).__name__


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 64
    sub = argv[1]
    try:
        if sub == "pre-commit":
            return cmd_pre_commit()
        if sub == "commit-msg" and len(argv) > 2:
            return cmd_commit_msg(argv[2])
        if sub == "claude-hook":
            return cmd_claude_hook(sys.stdin.read())
        if sub == "claude-post-hook":
            return cmd_claude_post_hook(sys.stdin.read())
        if sub == "pre-push":
            return cmd_pre_push(argv[2:])
        if sub in ("install", "uninstall") and len(argv) > 2:
            return cmd_install(argv[2], uninstall=(sub == "uninstall"))
        print(__doc__, file=sys.stderr)
        return 64
    except Exception as e:  # noqa: BLE001 - the guard must say it broke rather than die silently
        where = _where(e)
        if sub == "claude-hook":
            try:
                mode, _ = load_mode()
            except Exception:  # noqa: BLE001
                mode = "error"
            if mode in ("block", "error"):
                print(f"commit-guard: guard error ({where}), fix config/guard.py. Commit blocked "
                      "until the guard works.", file=sys.stderr)
                return CLAUDE_BLOCK_EXIT
        print(f"commit-guard: WARNING guard error ({where}), guard skipped; commit allowed.", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
