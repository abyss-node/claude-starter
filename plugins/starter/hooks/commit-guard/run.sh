#!/bin/sh
# Launcher for guard.py: picks the first working Python 3.8+ and exec's it, so the guard's exit code
# (2 = block) and stdin reach Claude Code unchanged and the guard runs exactly once.
# `python3 ... || python ...` would run the guard twice on a block, and a Windows Store alias stub
# ("python3" that opens the Store, exit 9009) must be skipped, hence the version probe.
# With no usable Python the guard is skipped with one stderr line: a missing interpreter never blocks a commit.
case $0 in */*) here=${0%/*} ;; *) here=. ;; esac  # no dirname: it may not be on PATH
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    exec "$py" "$here/guard.py" "$@"
  fi
done
echo "commit-guard: python 3.8+ not found, guard skipped" >&2
exit 0
