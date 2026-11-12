#!/bin/sh
set -eu
blueprint_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cache_root=${CLOUDGPT_CACHE_DIR:-"$blueprint_root/.cache"}
mkdir -p "$cache_root/npm" "$cache_root/uv"
npm --cache "$cache_root/npm" ci --no-audit --no-fund --prefix "$blueprint_root/runtimes/media"
UV_CACHE_DIR="$cache_root/uv" uv sync --frozen --project "$blueprint_root/runtimes/python"
printf '%s\n' 'Installed isolated media, MCP, transcription and download tools. Account login and MCP registration are separate verified steps.'
