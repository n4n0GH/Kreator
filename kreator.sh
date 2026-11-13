#!/bin/sh
# Run Kreator from the source tree.
PYTHONPATH="$(dirname "$(readlink -f "$0")")${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m kreator "$@"
