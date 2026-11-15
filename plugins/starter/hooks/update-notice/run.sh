#!/bin/sh
# SessionStart launcher for notice.py: picks the first working Python 3.9+ and exec's it, skipping a
# Windows Store alias stub (exit 9009) by the version probe, as commit-guard/run.sh does. With no usable
# Python it prints nothing and exits 0: a missing interpreter never delays or blocks a session.
case $0 in */*) here=${0%/*} ;; *) here=. ;; esac
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    exec "$py" "$here/notice.py"
  fi
done
exit 0
