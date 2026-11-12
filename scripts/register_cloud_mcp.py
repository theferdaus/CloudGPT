#!/usr/bin/env python3
"""Add verified portable MCP entries; preserve every existing entry and its state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def register(config, root=ROOT):
    config = Path(config)
    if config.is_symlink():
        raise ValueError("Refusing a symlink configuration file")
    original = config.read_bytes() if config.exists() else b""
    parsed = tomllib.loads(original.decode())
    existing = parsed.get("mcp_servers", {})
    blocks, added, preserved = [], [], []
    definitions = {
        "wavespeed": ('command = "node"\nargs = ' + json.dumps([str(root / 'runtimes/media/node_modules/@wavespeed/mcp/dist/index.js')]) +
                      '\nenv_vars = ["WAVESPEED_API_KEY"]\nstartup_timeout_sec = 60\n[mcp_servers.wavespeed.env]\nNODE_USE_ENV_PROXY = "1"\n'),
        "notebooklm": ('command = ' + json.dumps(str(root / 'runtimes/python/.venv/bin/notebooklm-mcp')) +
                       '\nenabled = false\nstartup_timeout_sec = 60\n'),
    }
    for name, text in definitions.items():
        if name in existing:
            preserved.append(name)
        else:
            blocks.append(f"\n# Added by CloudGPT portability setup. NotebookLM awaits cloud login.\n[mcp_servers.{name}]\n{text}")
            added.append(name)
    result = {"added": added, "preserved_existing": preserved, "original_sha256": hashlib.sha256(original).hexdigest(),
              "credential_values_written": False, "notebooklm_default": "disabled_pending_login"}
    if not blocks:
        result["changed"] = False
        return result
    updated = original + (b"\n" if original and not original.endswith(b"\n") else b"") + "".join(blocks).encode()
    tomllib.loads(updated.decode())
    config.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".cloudgpt-config-", dir=config.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(updated)
        if (config.read_bytes() if config.exists() else b"") != original:
            raise RuntimeError("Configuration changed during setup; preserved it")
        os.replace(temp, config)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()
    result["changed"] = True
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".codex/config.toml")
    args = parser.parse_args()
    print(json.dumps(register(args.config)))
