#!/bin/sh
# Runs scripts/jscheck.js (the browser code's static check, D-286) with the node that
# Playwright ships, so nothing is installed for it. With no arguments: every module
# under web/ but the vendored ones.
set -e
here=$(dirname "$0")
node=$(python -c 'import os, playwright; print(os.path.join(os.path.dirname(playwright.__file__), "driver", "node"))')
if [ $# -eq 0 ]; then
  set -- $(find "$here/../web" -name '*.js' -not -path '*/vendor/*' | sort)
fi
exec "$node" --expose-internals "$here/jscheck.js" "$@"
