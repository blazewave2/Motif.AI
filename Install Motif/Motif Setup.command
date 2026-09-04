#!/bin/bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$HERE/setup/motif_setup.py" "$@"
