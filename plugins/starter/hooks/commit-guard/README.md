# commit-guard

A check on every `git commit` an agent makes, and optionally on your own commits. It exists because printing a
secret once leaked a key, so findings show `file:line  rule-id` and never the value.

It scans added lines only (the staged diff, plus whatever the same command is about to stage), the commit message, and
the pushed commits.

## What it catches

| Rule id | What | Notes |
| --- | --- | --- |
| `aws-access-key`, `github-token`, `github-pat`, `anthropic-key`, `openai-key`, `google-api-key`, `slack-token`, `private-key`, `db-url-password` | Credentials | Placeholder DB passwords (`password`, `changeme`, `<...>`, `$VAR`) are ignored |
| `in-mobile` | Indian mobile number | Needs a `+91` or `0` prefix, or a phone word (phone, mobile, call, whatsapp, contact, tel) within 20 characters; never an `id`, `size` or `count` field |
| `aadhaar` | 12-digit Aadhaar number | First digit 2-9 and a valid Verhoeff checksum |
| `pan` | PAN card number | `AAAAA9999A` with a valid holder-type 4th letter (`PCHFATBLJG`) |
| `email` | Email address that is not yours | Warn-only in every mode; `noreply`, `example.*`, file-extension look-alikes and your own `user.email` are ignored |
| `ai-coauthor`, `ai-noreply`, `ai-generated-with` | Claude/Anthropic attribution lines in the message | Always blocks once the mode is block. The plugin's policy is that commits are attributed to you alone; to opt out for a repo, allowlist `commit-message` (see below) |
| `missing-verification-record` | No `Verified:` / `Unverified:` trailer | See below |

### The verification record

Every commit message needs a trailer in its last paragraph:

```
git commit -m "Fix retry loop" -m "Verified: pytest tests/ -> 152 passed"
git commit -m "Fix retry loop" -m "Unverified: reasoned about the retry path, nothing was run"
```

`Verified:` needs `<what was run> -> <result>`. Merges, `fixup!`/`squash!`, reverts, cherry-picks and in-progress
merges are exempt. Only commits authored on or after `record_required_from` (default `2026-11-07T00:00:00+05:30`)
are judged, so pushing old history is not blamed. `"require_record": false` in the config turns the rule off.

## Where the hooks come from

`hooks/hooks.json` wires `PreToolUse` (scan, can block) and `PostToolUse` (re-scan the commit that was just made, tell
the agent to `git commit --amend`; never blocks) for the `Bash` and `PowerShell` tools, only when the command matches
`git *commit*`. It acts only when the command really runs `git commit`; text that merely mentions it is ignored.

`run.sh` launches `guard.py` with the first working Python 3.9+ (`python3`, `python`, `py`) and passes the exit code
through unchanged (exit 2 is what blocks). If no Python is found it prints one line to stderr and lets the commit
through: a missing interpreter never blocks you. Hook commands run through `sh`, so on Windows you need Git for
Windows (Claude Code's normal setup).

## Where state lives

The plugin directory is a cache that is replaced on every update, so nothing mutable lives there. State lives in
`~/.claude/commit-guard/` (or `$CLAUDE_CONFIG_DIR/commit-guard/`; override the whole directory with
`COMMIT_GUARD_DIR`):

| File | What |
| --- | --- |
| `config.json` | Mode and options. Optional |
| `bypass.log` | Appended on every human bypass |
| `trusted-repos.txt` | Repos whose own `.claude/checks/` scripts may run (one path per line) |
| `state/` | Short-lived files that let the post-commit check find the commits it should scan |
| `guard.py` | Copy used by git hooks installed with `install` (below) |

Individual files can be moved with `COMMIT_GUARD_CONFIG`, `COMMIT_GUARD_BYPASS_LOG`, `COMMIT_GUARD_TRUSTED` and
`COMMIT_GUARD_STATE`.

## Modes

With no `config.json` the mode is **warn**: problems are printed (and shown to the agent), and the commit goes
through. To switch to blocking, create `~/.claude/commit-guard/config.json`:

```json
{"mode": "block"}
```

To switch on a date instead, keep `"mode": "warn"` and add `"block_from": "2026-12-01"`. An invalid config (wrong
types, bad date) is a config error: agents are blocked with "fix config", a human's git hooks are not. Other options:
`require_record` (bool), `record_required_from` (ISO date-time), `pre_push_max_commits` (default 1000).

Warn-only rules (`email`) never block in any mode. If the guard itself crashes, agents are blocked once the mode is
block, and let through before that.

## Bypass (humans only)

In your own terminal, `COMMIT_GUARD_BYPASS=1 git commit ...` skips the guard for that commit and appends a line to
`bypass.log`; set `COMMIT_GUARD_REASON="why"` to record a reason. The agent hook refuses any `git commit` whose command
mentions `COMMIT_GUARD*`, `core.hooksPath`, `--no-verify` or `-n`, in every mode, so an agent cannot bypass it.

## Per-repo allowlist

`.claude/checks/allowlist.txt` in a repo, one `path-glob:rule-id` per line (`*` for any rule); `#` starts a comment:

```
fixtures/*:aws-access-key
*.csv:email
commit-message:ai-coauthor
```

## Repo checks

Scripts (`.sh`, `.py`, `.ps1`) in a repo's `.claude/checks/` run on commit, but only for repos listed in
`trusted-repos.txt`, because a third-party repo can ship arbitrary scripts there. Other repos get a one-line "skipped"
note.

## Hooks for your own commits (opt in, per repo)

```
python <plugin dir>/hooks/commit-guard/guard.py install /path/to/repo
python <plugin dir>/hooks/commit-guard/guard.py uninstall /path/to/repo
```

`install` writes `pre-commit`, `commit-msg` and `pre-push` into the repo's hooks directory (a `core.hooksPath` inside
the repo is respected; one outside it is refused). An existing hook of the same name is kept as `<name>.local` and
called first; `uninstall` restores it. A broken Python or a guard crash never blocks a human, only the guard's own
block code does. `pre-push` also scans the diffs of the pushed commits for secrets.

`install` copies `guard.py` to `~/.claude/commit-guard/guard.py` and points the hooks at that copy, because the
plugin directory changes on update and would break a hook that named it. The copy does not update itself: re-run
`install` for each repo after a plugin update to pick up new rules (re-running is safe).

## False positives

Prefer the allowlist over a bypass. The rules are deliberately narrow, each earned from a false positive: Aadhaar needs
the Verhoeff checksum, a mobile number needs a prefix or a phone word nearby, PAN needs a valid holder-type letter,
database URLs with placeholder passwords are ignored. If a rule still fires on a test fixture, allowlist that path and
rule.

## Tests

`cd hooks/commit-guard/tests && python -m pytest -q`
