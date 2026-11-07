#!/usr/bin/env python3
"""Opt-in, redacted failure report for claude-starter.

Builds a report about a failure (install failed, commit guard misfired, an agent misbehaved), strips
private data from every string in it, and shows it to you. By default NOTHING is sent: the report is
printed, saved to a file, and a pre-filled GitHub issue link is printed for you to open yourself.
`--submit` files the issue with `gh` only after you confirm.

    python scripts/report.py --kind install-failure --step "installing the OpenCode adapter" \
        --error-file install.log --tool opencode

Importable API: build_report(kind, step, error_text, extra=None), render_markdown(report).

Every outbound path (the saved file, the issue URL, `gh issue create`) takes the RenderedReport that
render_markdown returns, and render_markdown redacts again, so unredacted text cannot reach them.

Python 3.9+, standard library only. The secret and PII detectors are loaded from the commit guard so
the two never drift apart.
"""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

REPO = "abyss-node/claude-starter"
KINDS = ("install-failure", "guard-false-positive", "agent-misbehaved")
KNOWN_TOOLS = ("opencode", "codex", "gemini", "claude")
MAX_ERROR_LINES = 200
MAX_LINE_CHARS = 2000
URL_CAP = 7000
VERSION_TIMEOUT = 8
KIT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = KIT_ROOT / "plugins" / "starter" / ".claude-plugin" / "plugin.json"
GUARD_PATH = KIT_ROOT / "plugins" / "starter" / "hooks" / "commit-guard" / "guard.py"
TRUNC_MARK = "[...truncated; paste the saved report file for the full text...]"


# --------------------------------------------------------------------------
# Detectors, reused from the commit guard
# --------------------------------------------------------------------------

def _load_guard():
    if not GUARD_PATH.is_file():
        raise SystemExit("report.py: cannot find the commit guard at %s. Redaction reuses its detectors, "
                         "so this refuses to run without it." % GUARD_PATH)
    spec = importlib.util.spec_from_file_location("commit_guard_detectors", str(GUARD_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_GUARD = _load_guard()


# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------

_DRIVE_RE = re.compile(r"^[A-Za-z]:$")
_NAME = r"[^\\/\s\"<>:|*?`]+"  # apostrophes are legal in Windows usernames
# A name may hold spaces ("Mary O'Neil"); the extra words count only when a path separator follows, so
# prose after a bare home path is not swallowed.
_HOME_NAME = r"(?:%s(?: %s){1,2}(?=[\\/])|%s)" % (_NAME, _NAME, _NAME)
# Home-shaped paths of anyone, as a backstop when the real home differs from what we detected.
_GENERIC_HOMES = [
    re.compile(r"(?:[A-Za-z]:|/[A-Za-z]|/mnt/[A-Za-z])[\\/]+Users[\\/]+" + _HOME_NAME, re.I),
    re.compile(r"(?<![\w.~-])/(?:home|Users)/" + _HOME_NAME),
    re.compile(r"(?<![\w.~-])/root(?![\w-])"),
]
# The same homes URL-encoded (C%3A%5CUsers%5Cname, %2Fhome%2Fname), as in a file= query string.
_ENC_SEP = r"(?:%5C|%2F)+"
_ENC_NAME = r"(?:[^\s%&?#/\\\"<>=]|%(?!5C|2F)[0-9A-F]{2})+"
_ENC_HOME = re.compile(r"(?:[A-Za-z]%3A|%2F[A-Za-z](?=%2F)|%2Fmnt%2F[A-Za-z](?=%2F))?" + _ENC_SEP
                       + r"(?:Users|home)" + _ENC_SEP + _ENC_NAME, re.I)
_HOME_VARS = re.compile(r"\$\{HOME\}|\$HOME(?![A-Za-z0-9_])|%USERPROFILE%|\$env:USERPROFILE", re.I)
_CRED_URL = re.compile(r"(://)[^\s/@:'\"]+:[^\s/@'\"]+@")
_BEARER = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.I)
# A whole private key block, body included: PEM (-----BEGIN ...-----) and SSH2 (---- BEGIN ... ----).
# A log cut off before END loses everything after BEGIN.
_PEM = re.compile(r"-{4,5} ?BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)? ?-{4,5}.*?"
                  r"(?:-{4,5} ?END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)? ?-{4,5}|\Z)", re.S)
# PuTTY .ppk: the private part is the N lines after "Private-Lines: N", then a MAC over it.
_PPK_LINES = re.compile(r"^[ \t]*Private-Lines:[ \t]*(\d+)[ \t\r]*$")
_PPK_MAC = re.compile(r"^([ \t]*Private-(?:MAC|Hash):[ \t]*)\S+", re.M)
_B64_LINE = re.compile(r"^[ \t]*[A-Za-z0-9+/=]+[ \t\r]*$")
# What is left of a key whose BEGIN line was lost: a run of 3+ base64 lines, or a stray END line.
_FRAGMENT_LINE = re.compile(r"^[ \t]*[A-Za-z0-9+/=]{40,}[ \t\r]*$")
_FRAGMENT_END = re.compile(r"-{4,5} ?END [A-Z0-9 ]*KEY(?: BLOCK)? ?-{4,5}")
FRAGMENT_RUN = 3
# Token shapes the commit guard does not know (it scans diffs, this scans logs). Report-side only.
_TOKENS = [
    ("stripe-key", re.compile(r"(?<![A-Za-z0-9])[sr]k_(?:live|test)_[A-Za-z0-9]{10,}")),
    ("npm-token", re.compile(r"(?<![A-Za-z0-9])npm_[A-Za-z0-9]{36}(?![A-Za-z0-9])")),
    ("huggingface-token", re.compile(r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{30,}")),
    ("stripe-webhook-secret", re.compile(r"(?<![A-Za-z0-9])whsec_[A-Za-z0-9+/=]{16,}")),
    ("jwt", re.compile(r"(?<![\w-])eyJ[\w-]+=*\.eyJ[\w-]+=*\.[\w-]*=*")),  # some encoders keep the padding
]
_AWS_SECRET_CONTEXT = re.compile(r"aws.{0,20}secret|secret.?access.?key", re.I)
_AWS_SECRET = re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])")
_AUTH_HEADER = re.compile(r"\b((?:Proxy-)?Authorization[\"']?[ \t]*:[ \t]*[\"']?)([^\r\n\"']+)", re.I)
_AUTH_SCHEME = re.compile(r"(?:Basic|Bearer|Token|Digest|Negotiate|NTLM)[ \t]+", re.I)
_COOKIE_HEADER = re.compile(r"\b((?:Set-)?Cookie[\"']?[ \t]*:[ \t]*[\"']?)([^\r\n\"']+)", re.I)
# `auth` counts only as a whole word part (basicAuth, _auth), so author/authority/authentication survive.
_SECRET_WORD = r"(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH(?:ORIZATION)?(?![A-Za-z]))"
_ENV_ASSIGN = re.compile(
    r"(?P<name>[A-Za-z0-9_.-]*" + _SECRET_WORD + r"[A-Za-z0-9_.-]*)(?P<sep>[\"']?[ \t]*[:=][ \t]*)"
    r"(?!<redacted|(?:Basic|Bearer|Token|Digest|Negotiate|NTLM)[ \t]+<redacted)"
    r"(?P<val>\"[^\"\n]*\"|'[^'\n]*'|[^\s,;]+)", re.I)
_ENV_NAME_SKIP = re.compile(r"(?:Error|Exception|Warning|Exit)$", re.I)
_CLI_FLAG = re.compile(r"(?P<flag>--[A-Za-z0-9-]*(?:key|token|secret|password|passwd)[A-Za-z0-9-]*)"
                       r"(?P<sep>[ =])(?!<redacted|-)(?P<val>\"[^\"\n]*\"|'[^'\n]*'|\S+)", re.I)
_IPV4 = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w])")
_H = r"[0-9A-Fa-f]{1,4}"
_IPV6 = [
    re.compile(r"(?<![\w:])(?:%s:){7}%s(?![\w:])" % (_H, _H)),
    re.compile(r"(?<![\w:])(?:%s:){1,7}:(?:%s(?::%s){0,6})?(?![\w:])" % (_H, _H, _H)),
    re.compile(r"(?<![\w:])::(?:%s:){0,6}%s(?![\w:])" % (_H, _H)),
]


MIN_BARE_USER = 4


class Identity:
    """Who is running this: home dir forms, usernames, hostname.

    A username shorter than MIN_BARE_USER characters ("bob", "dev") is an ordinary word too often to
    replace wherever it appears; it is redacted only as part of a home path. A name with spaces is also
    redacted word by word, so "Mary O'Neil" cannot leave "O'Neil" behind."""

    def __init__(self, homes, users, hosts):
        self.homes = [h for h in homes if h]
        names = set()
        for u in (u for u in users if u):
            names.add(u)
            names.update(w for w in u.split() if w != u)
        self.users = sorted((u for u in names if len(u) >= MIN_BARE_USER), key=len, reverse=True)
        keep = {h.strip().rstrip(".") for h in hosts if h}
        self.hosts = sorted((h for h in keep if len(h) >= 4 and not h.lower().startswith("localhost")
                             and not h.lower().endswith(".arpa") and not _IPV4.fullmatch(h)),
                            key=len, reverse=True)


def _identity() -> Identity:
    homes, users = [], []
    try:
        homes.append(str(Path.home()))
    except Exception:  # noqa: BLE001 - no resolvable home is not a reason to skip redaction
        pass
    for var in ("HOME", "USERPROFILE"):
        if os.environ.get(var):
            homes.append(os.environ[var])
    for var in ("USERNAME", "USER", "LOGNAME"):
        if os.environ.get(var):
            users.append(os.environ[var])
    try:
        users.append(getpass.getuser())
    except Exception:  # noqa: BLE001
        pass
    for h in homes:
        parts = [p for p in re.split(r"[\\/]+", h) if p]
        if parts:
            users.append(parts[-1])
    extra = []
    for u in users:  # "O'Neil" is also written "ONeil" by tools that strip punctuation
        stripped = re.sub(r"[^A-Za-z0-9]", "", u)
        if stripped != u:
            extra.append(stripped)
    hosts = [os.environ.get(v, "") for v in ("COMPUTERNAME", "HOSTNAME")]
    for probe in (socket.gethostname, socket.getfqdn):
        try:
            hosts.append(probe())
        except Exception:  # noqa: BLE001 - a failed lookup is not a reason to skip redaction
            pass
    return Identity(homes, users + extra, hosts)


def _home_regex(home: str):
    parts = [p for p in re.split(r"[\\/]+", home) if p]
    if not parts:
        return None
    if _DRIVE_RE.match(parts[0]):
        d = re.escape(parts[0][0])
        head = r"(?:%s:|/%s|/mnt/%s)" % (d, d, d)
        rest = parts[1:]
    else:
        head = ""
        rest = parts
    body = "".join(r"[\\/]+" + re.escape(p) for p in rest)
    if not head and not body:
        return None
    return re.compile((r"(?<![\w.~-])" if not head else "") + head + body + r"(?![A-Za-z0-9_])", re.I)


def _user_regex(user: str):
    """The username as a whole word, also URL-encoded (O%27Neil, Mary%20O%27Neil, Mary+O'Neil). An
    encoded neighbour counts as a boundary: the C of %5C must not hide the name that follows it."""
    parts = []
    for ch in user:
        if ch.isascii() and ch.isalnum():
            parts.append(re.escape(ch))
        elif ch.isspace():
            parts.append(r"(?:[ \t]+|%20|\+)")
        else:
            parts.append("(?:%s|%s)" % (re.escape(ch), re.escape(quote(ch, safe=""))))
    return re.compile(r"(?:(?<![A-Za-z0-9])|(?<=%[0-9A-Fa-f]{2}))" + "".join(parts) + r"(?![A-Za-z0-9])",
                      re.I)


def _redact_ppk(text: str) -> str:
    if "Private-" not in text:
        return text
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        out.append(lines[i])
        m = _PPK_LINES.match(lines[i])
        i += 1
        if m:
            j = i
            while j < len(lines) and j - i < int(m.group(1)) and _B64_LINE.match(lines[j]):
                j += 1
            if j > i:
                out.append("<redacted:private-key>")
            i = j
    return _PPK_MAC.sub(lambda m: m.group(1) + "<redacted:private-key>", "\n".join(out))


def _fragment_line(line: str) -> bool:
    # Mixed case as well: a column of 40-character lowercase hex (git commit ids) is not key material.
    return bool(_FRAGMENT_LINE.match(line) and re.search("[A-Z]", line) and re.search("[a-z]", line))


def _redact_key_fragments(text: str) -> str:
    """Key material whose BEGIN line is gone: a run of FRAGMENT_RUN or more long base64 lines, and any
    END ... KEY line. Each run becomes one placeholder line."""
    text = _FRAGMENT_END.sub("<redacted:key-fragment>", text)
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        j = i
        while j < len(lines) and _fragment_line(lines[j]):
            j += 1
        if j - i >= FRAGMENT_RUN:
            out.append("<redacted:key-fragment>")
            i = j
        else:
            out.extend(lines[i:j + 1])
            i = j + 1
    return "\n".join(out)


def redact(text: str, ident: Identity | None = None) -> str:
    """Return text with secrets, PII, home paths, usernames, emails and IPs replaced by placeholders."""
    if not text:
        return text
    ident = ident or _identity()
    g = _GUARD

    # 1. Secrets: whole private keys and key fragments first, then the commit guard's rules, then
    #    report-only shapes.
    text = _PEM.sub("<redacted:private-key>", text)
    text = _redact_ppk(text)
    text = _redact_key_fragments(text)
    for rule, rx in g.SECRET_RULES:
        text = rx.sub("<redacted:%s>" % rule, text)
    for rule, rx in _TOKENS:
        text = rx.sub("<redacted:%s>" % rule, text)
    text = "\n".join(_AWS_SECRET.sub("<redacted:aws-secret-key>", ln) if _AWS_SECRET_CONTEXT.search(ln) else ln
                     for ln in text.split("\n"))

    def auth_sub(m):
        scheme = _AUTH_SCHEME.match(m.group(2))
        return m.group(1) + (scheme.group(0) if scheme else "") + "<redacted:authorization>"
    text = _AUTH_HEADER.sub(auth_sub, text)
    text = _COOKIE_HEADER.sub(lambda m: m.group(1) + "<redacted:cookie>", text)
    text = _BEARER.sub(lambda m: m.group(1) + "<redacted:bearer-token>", text)
    text = _CRED_URL.sub(lambda m: m.group(1) + "<redacted:url-credentials>@", text)
    text = _CLI_FLAG.sub(lambda m: m.group("flag") + m.group("sep") + "<redacted:cli-secret>", text)

    def env_sub(m):
        if _ENV_NAME_SKIP.search(m.group("name")):
            return m.group(0)
        return m.group("name") + m.group("sep") + "<redacted:env-secret>"
    text = _ENV_ASSIGN.sub(env_sub, text)

    # 2. PII the guard knows about, line by line so its context checks apply.
    lines = []
    for line in text.split("\n"):
        if g._mobile_hit(line):
            line = g.MOBILE_RE.sub("<redacted:in-mobile>", line)
        line = g.AADHAAR_RE.sub(
            lambda m: "<redacted:aadhaar>" if g.verhoeff_valid(re.sub(r"\s", "", m.group(0))) else m.group(0),
            line)
        line = g.PAN_RE.sub("<redacted:pan>", line)
        lines.append(line)
    text = "\n".join(lines)
    text = g.EMAIL_RE.sub("<email>", text)

    # 3. Home directory, in every spelling, then hostnames, then the bare username. Hosts go before
    #    users: a host named after its user ("name-ThinkPad") would otherwise lose only the name part.
    for home in sorted(ident.homes, key=len, reverse=True):
        rx = _home_regex(home)
        if rx:
            text = rx.sub("~", text)
    text = _HOME_VARS.sub("~", text)
    for rx in _GENERIC_HOMES:
        text = rx.sub("~", text)
    text = _ENC_HOME.sub("~", text)
    for h in ident.hosts:  # longest first; a trailing .domain suffix goes with the name
        text = re.sub(r"(?<![A-Za-z0-9])" + re.escape(h) + r"(?:\.[A-Za-z0-9-]+)*(?![A-Za-z0-9-])", "<host>",
                      text, flags=re.I)
    for u in ident.users:
        text = _user_regex(u).sub("<user>", text)

    # 4. IP addresses are dropped.
    text = _IPV4.sub("<ip>", text)
    for rx in _IPV6:
        text = rx.sub("<ip>", text)
    return text


def _redact_obj(obj, ident):
    if isinstance(obj, str):
        return redact(obj, ident)
    if isinstance(obj, dict):
        return {redact(str(k), ident): _redact_obj(v, ident) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redact_obj(v, ident) for v in obj]
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return redact(str(obj), ident)


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------

def _run_version(tool: str) -> str | None:
    exe = shutil.which(tool)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=VERSION_TIMEOUT,
                           stdin=subprocess.DEVNULL)
        out = (r.stdout or r.stderr or b"").decode("utf-8", "replace").strip()
        return out.splitlines()[0][:120] if out else "unknown"
    except Exception:  # noqa: BLE001 - version detection is best effort and must never fail the report
        return "unknown"


def _kit_info() -> dict:
    info = {"version": "unknown", "commit": None}
    try:
        import json
        info["version"] = json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version", "unknown")
    except Exception:  # noqa: BLE001
        pass
    if (KIT_ROOT / ".git").exists() and shutil.which("git"):
        try:
            r = subprocess.run(["git", "-C", str(KIT_ROOT), "rev-parse", "--short", "HEAD"],
                               capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
            if r.returncode == 0:
                info["commit"] = r.stdout.decode().strip()
                d = subprocess.run(["git", "-C", str(KIT_ROOT), "status", "--porcelain"],
                                   capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
                if d.returncode == 0 and d.stdout.strip():
                    info["commit"] += "+dirty"
        except Exception:  # noqa: BLE001
            pass
    return info


def _tail(text: str) -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    dropped = max(0, len(lines) - MAX_ERROR_LINES)
    lines = [l if len(l) <= MAX_LINE_CHARS else l[:MAX_LINE_CHARS] + " [...line cut...]"
             for l in lines[-MAX_ERROR_LINES:]]
    out = "\n".join(lines).strip("\n")
    if dropped:
        out = "[... %d earlier lines omitted ...]\n%s" % (dropped, out)
    return out


def build_report(kind: str, step: str, error_text: str, extra: dict | None = None,
                 tool: str | None = None, version_note: str | None = None) -> dict:
    """Collect environment facts and return a report dict with every string already redacted.

    version_note, when given, is recorded instead of running `<tool> --version`: a failure that happened
    before the install touched the tool must not have the report run it (codex writes into its home)."""
    if kind not in KINDS:
        raise ValueError("kind must be one of %s, got %r" % (", ".join(KINDS), kind))
    if tool:
        versions = {tool: version_note or (_run_version(tool) if tool in KNOWN_TOOLS else None)}
        detected = {}
    else:
        versions = {}
        detected = {} if version_note else {t: v for t in KNOWN_TOOLS for v in [_run_version(t)] if v}
    kit = _kit_info()
    ident = _identity()
    report = {
        "kind": kind,
        "step": step or "",
        "tool": {"name": tool, "version": versions.get(tool) if tool else None},
        "detected_tools": detected,
        "os": "%s %s (%s)" % (platform.system(), platform.release(), platform.machine()),
        "python": platform.python_version(),
        "kit_version": kit["version"],
        "kit_commit": kit["commit"],
        # Redacted whole, then cut: cutting first can drop a key's BEGIN line or shorten a token
        # below its pattern, and what is left of either then passes as ordinary text.
        "error": _tail(redact(error_text or "", ident)),
        "extra": dict(extra or {}),
    }
    if version_note and not tool:
        report["versions_note"] = version_note
    return _redact_obj(report, ident)


# --------------------------------------------------------------------------
# Rendering: the only producer of text that may leave the machine
# --------------------------------------------------------------------------

class RenderedReport(str):
    """Redacted markdown. Only render_markdown creates one; senders refuse plain strings."""
    sections: dict
    kind: str


def _fence(text: str) -> str:
    longest = max([len(m) for m in re.findall(r"`+", text)] or [0])
    return "`" * max(3, longest + 1)


def render_markdown(report: dict) -> RenderedReport:
    ident = _identity()
    r = _redact_obj(report, ident)  # idempotent: a raw dict cannot get past this
    kind = r.get("kind", "")
    if kind not in KINDS:
        raise ValueError("report has no valid kind")
    tool = r.get("tool") or {}
    env = []
    if tool.get("name"):
        env.append("- Tool: %s %s" % (tool["name"], tool.get("version") or "(version not detected)"))
    else:
        env.append("- Tool: not specified")
    det = r.get("detected_tools") or {}
    if r.get("versions_note"):
        env.append("- Tools on PATH: %s" % r["versions_note"])
    if det:
        env.append("- Tools found on PATH: " + ", ".join("%s %s" % (k, v) for k, v in det.items()))
    commit = r.get("kit_commit")
    env.append("- Kit: %s%s" % (r.get("kit_version", "unknown"), " (commit %s)" % commit if commit else ""))
    env.append("- OS: %s" % r.get("os", "unknown"))
    env.append("- Python: %s" % r.get("python", "unknown"))
    extra = r.get("extra") or {}
    sections = {
        "step": str(r.get("step", "")).strip() or "(not given)",
        "error": str(r.get("error", "")).strip() or "(none provided)",
        "environment": "\n".join(env),
        "extra": "\n".join("- %s: %s" % (k, v) for k, v in extra.items()),
    }
    fence = _fence(sections["error"])
    md = ["<!-- claude-starter report, kind: %s; redacted by scripts/report.py -->" % kind,
          "## What I was doing", sections["step"], "",
          "## Error output", "%stext" % fence, sections["error"], fence, "",
          "## Environment", sections["environment"], ""]
    if sections["extra"]:
        md += ["## Extra", sections["extra"], ""]
    out = RenderedReport("\n".join(md))
    out.sections = sections
    out.kind = kind
    return out


def _require_rendered(rendered) -> None:
    if not isinstance(rendered, RenderedReport):
        raise TypeError("only the output of render_markdown() may be saved, linked or sent")


# --------------------------------------------------------------------------
# Output paths: file, URL, gh
# --------------------------------------------------------------------------

def issue_title(rendered: RenderedReport) -> str:
    step = " ".join(rendered.sections["step"].split())
    if len(step) > 70:
        step = step[:67] + "..."
    return "[%s] %s" % (rendered.kind, step)


def issue_url(rendered: RenderedReport, cap: int = URL_CAP):
    """Pre-filled new-issue URL for the matching issue form. Returns (url, truncated)."""
    _require_rendered(rendered)
    fields = {k: v for k, v in rendered.sections.items() if v}
    title = issue_title(rendered)

    def build() -> str:
        q = ["template=%s.yml" % rendered.kind, "title=" + quote(title, safe="")]
        q += ["%s=%s" % (k, quote(v, safe="")) for k, v in fields.items()]
        return "https://github.com/%s/issues/new?%s" % (REPO, "&".join(q))

    truncated = False
    url = build()
    while len(url) > cap:
        truncated = True
        # shrink whichever field costs the most encoded characters
        key = max(fields, key=lambda k: len(quote(fields[k], safe="")))
        val = fields[key]
        if len(val) <= len(TRUNC_MARK) + 20:
            del fields[key]
        elif key == "error":  # keep the end of the log, that is where the failure is
            fields[key] = TRUNC_MARK + "\n" + val[len(TRUNC_MARK) + 1:][-int(len(val) * 0.7):]
        else:
            fields[key] = val[:int(len(val) * 0.7)] + " " + TRUNC_MARK
        url = build()
        if not fields:
            break
    return url, truncated


def save_report(rendered: RenderedReport, path: str | None) -> Path:
    _require_rendered(rendered)
    p = Path(path) if path else Path.cwd() / ("claude-starter-report-%s.md" % time.strftime("%Y%m%d-%H%M%S"))
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(str(rendered))
    return p


def _gh_ready() -> bool:
    if not shutil.which("gh"):
        return False
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=30,
                              stdin=subprocess.DEVNULL).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def submit_issue(rendered: RenderedReport, yes: bool = False, out=print) -> str | None:
    """File the issue with gh after confirmation. Returns the issue URL, or None if nothing was sent."""
    _require_rendered(rendered)
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive and not yes:
        out("Not sending: no terminal to confirm on. Re-run with --yes to send non-interactively.")
        return None
    if not _gh_ready():
        out("Not sending: `gh` is missing or not signed in (`gh auth login`).")
        return None
    if not yes:
        try:
            answer = input("Send this as a public GitHub issue? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            out("Not sent.")
            return None
    fd, tmp = tempfile.mkstemp(prefix="claude-starter-report-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(str(rendered))
        base = ["gh", "issue", "create", "--repo", REPO, "--title", issue_title(rendered), "--body-file", tmp]
        r = subprocess.run(base + ["--label", rendered.kind], capture_output=True, timeout=120,
                           stdin=subprocess.DEVNULL)
        if r.returncode != 0 and b"label" in (r.stderr or b"").lower():
            r = subprocess.run(base, capture_output=True, timeout=120, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            out("gh could not create the issue: " + (r.stderr or b"").decode("utf-8", "replace").strip())
            return None
        url = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        return url[-1] if url else ""
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

# Git Bash leaves `/c/Users/...` unconverted when an argument holds an apostrophe (a home folder like
# O'Neil), and Windows Python then reads it as C:\c\Users\... on the current drive.
_MISCONVERTED = re.compile(r"^[A-Za-z]:[\\/]+[A-Za-z][\\/]+(?:Users|home)(?:[\\/]|$)", re.I)
RECLONE_PS = r'git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"'


def misconverted_path(path: str) -> bool:
    """True for a path like C:/c/Users/x (or with backslashes): a Git Bash path Windows read literally."""
    return bool(_MISCONVERTED.match(str(path)))


def misconverted_warning(paths) -> str | None:
    bad = [str(p) for p in paths if misconverted_path(str(p))]
    if not bad:
        return None
    return ("WARNING: running from %s\n"
            "  That looks like a Git Bash path Windows read literally (/c/Users/... became C:\\c\\Users\\...),\n"
            "  which happens when the home folder name contains an apostrophe. Files may land in the wrong\n"
            "  place. Re-clone from PowerShell and use the PowerShell commands in README.md:\n"
            "    %s" % (bad[0], RECLONE_PS))


def _read_error_file(path: str) -> str:
    data = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # PowerShell redirects write UTF-16
        return data.decode("utf-16", "replace")
    return data.decode("utf-8-sig", "replace")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="Build a redacted failure report. Nothing is sent unless --submit.")
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--step", required=True, help="what was being done when it failed")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--error-file", help="file with the error output ('-' for stdin)")
    src.add_argument("--error", help="error text")
    ap.add_argument("--tool", help="tool being installed into or used (opencode, codex, gemini, claude, cursor, ...)")
    ap.add_argument("--submit", action="store_true", help="file a public issue with gh, after confirmation")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt (required when not on a terminal)")
    ap.add_argument("--out", help="where to save the report (default: ./claude-starter-report-<timestamp>.md)")
    args = ap.parse_args(argv)
    warning = misconverted_warning([__file__, KIT_ROOT])
    if warning:
        print(warning, file=sys.stderr)

    if args.error_file:
        try:
            error_text = _read_error_file(args.error_file)
        except OSError as e:
            print("Cannot read --error-file: %s" % e, file=sys.stderr)
            return 2
    else:
        error_text = args.error or ""

    rendered = render_markdown(build_report(args.kind, args.step, error_text, tool=args.tool))
    saved = save_report(rendered, args.out)
    url, truncated = issue_url(rendered)

    print(rendered)
    print("-" * 60)
    print("Saved: %s" % redact(str(saved)))
    print("This report is redacted but read it before sharing: it becomes public if you post it.")
    sent = None
    if args.submit:
        sent = submit_issue(rendered, yes=args.yes)
        if sent is not None:
            print("Issue created: %s" % sent)
    if sent is None:
        print("Nothing has been sent. To file it yourself, open:")
        print(url)
        if truncated:
            print("The link holds a shortened copy (GitHub limits URL length). Paste the full saved file "
                  "into the form instead.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
