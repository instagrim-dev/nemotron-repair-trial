#!/bin/sh
# Run from any working directory; no credentials or network calls are required.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
test -s README.md
test -s LICENSE
grep -qx 'MIT License' LICENSE
for directory in agent providers/nebius workspace verifier evaluation; do
  test -d "$directory"
done
printf 'Scaffold checks passed.\n'
