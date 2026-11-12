#!/bin/sh
set -eu
blueprint_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
skills_destination=${CLOUDGPT_SKILLS_DIR:-/workspace/.agents/skills}
python3 "$blueprint_root/scripts/bootstrap.py" --skills-dir "$skills_destination"
python3 "$blueprint_root/scripts/audit.py" --label cloud --project "$blueprint_root" --project /workspace --output "$blueprint_root/reports/cloud-filesystem.json"
