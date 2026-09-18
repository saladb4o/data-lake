#!/usr/bin/env bash
# Build the VAS template from a copy of the CFI model, then quiet the cells
# that are only waiting for the user's comparables.
#
#   scripts/xlsxvas/make_template.sh SOURCE.xlsx OUT.xlsx
#
# The second step needs LibreOffice Calc, because the list of cells to
# quiet is read off a real evaluation rather than written by hand.
set -euo pipefail
src="$1"; out="$2"
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
python3 "$here/build_vas_template.py" "$src" "$tmp/step1.xlsx"
python3 "$here/wrap_pending_inputs.py" "$tmp/step1.xlsx" "$out"
rm -rf "$tmp"
