#!/bin/sh
set -eu
blueprint_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cache_root=${CLOUDGPT_CACHE_DIR:-"$blueprint_root/.cache"}
mkdir -p "$cache_root/huggingface" "$cache_root/hyperframes-history" "$cache_root/hyperframes-fonts"
PATH="$blueprint_root/runtimes/media/node_modules/.bin:$blueprint_root/runtimes/python/.venv/bin:$PATH"
export PATH
export NODE_USE_ENV_PROXY=${NODE_USE_ENV_PROXY:-1}
export HF_HOME=${HF_HOME:-"$cache_root/huggingface"}
export HYPERFRAMES_HISTORY_ROOT=${HYPERFRAMES_HISTORY_ROOT:-"$cache_root/hyperframes-history"}
export HYPERFRAMES_FONT_CACHE_DIR=${HYPERFRAMES_FONT_CACHE_DIR:-"$cache_root/hyperframes-fonts"}
if [ -z "${HYPERFRAMES_BROWSER_PATH:-}" ] && command -v chromium >/dev/null 2>&1; then
  HYPERFRAMES_BROWSER_PATH=$(command -v chromium)
  export HYPERFRAMES_BROWSER_PATH
fi
exec "$@"
