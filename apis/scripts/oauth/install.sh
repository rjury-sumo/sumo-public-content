#!/usr/bin/env bash
# Install sumo-oauth using native Python (no uv required).
#
# Option A: installs as an editable package, registers the `sumo-oauth` command.
# After running this script, activate the venv and use `sumo-oauth` directly:
#
#   source .venv/bin/activate
#   sumo-oauth users --filter "@example.com"
#
# Option B (commented out): install deps only, run the script directly.
#   source .venv/bin/activate
#   python3 sumo_oauth.py users --filter "@example.com"

set -euo pipefail

cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate

# Option A — editable install (registers the sumo-oauth entrypoint)
pip install -e .

# Option B — dependencies only, no entrypoint
# pip install keyring requests

echo ""
echo "Done. To activate the environment:"
echo "  source $(pwd)/.venv/bin/activate"
echo ""
echo "Then run:"
echo "  sumo-oauth --help"
