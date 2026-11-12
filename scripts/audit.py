#!/usr/bin/env python3
"""Allowlist-based host inventory. Never serializes raw config or command output."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tomllib
from urllib.parse import urlsplit

UNKNOWN = "unknown"
TOKEN = re.compile(r"(?:sk-[\w-]{12,}|gh[pousr]_[\w]{12,}|github_pat_[\w_]{12,}|Bearer\s+\S+|[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*\S+)", re.I)
TOOLS = {
    "git": ["--version"], "gh": ["--version"], "python3": ["--version"],
    "uv": ["--version"], "node": ["--version"], "npm": ["--version"],
    "pnpm": ["--version"], "bun": ["--version"], "ffmpeg": ["-version"],
    "ffprobe": ["-version"], "docker": ["--version"], "go": ["version"],
    "rustc": ["--version"], "cargo": ["--version"], "java": ["-version"],
    "pandoc": ["--version"], "typst": ["--version"], "pdflatex": ["--version"],
    "jq": ["--version"], "rg": ["--version"], "codex": ["--version"],
    "xcodebuild": ["-version"], "swift": ["--version"], "brew": ["--version"]
}


def clean(value):
    return TOKEN.sub("[REDACTED]", str(value))[:2000]


def identifier(value):
    return clean(value)[:250]


def endpoint(value):
    try:
        u = urlsplit(str(value))
        return {"scheme": u.scheme, "host": u.hostname, "port": u.port}
    except ValueError:
        return {"status": "unparseable"}


def load(path, warnings):
    try:
        raw = path.read_bytes()
        return tomllib.loads(raw.decode()) if path.suffix == ".toml" else json.loads(raw)
    except (OSError, ValueError) as exc:
        warnings.append({"path": str(path), "status": type(exc).__name__})
        return {}


def command_probe(name, args):
    path = shutil.which(name)
    row = {"name": name, "path": path, "present": bool(path), "runnable": UNKNOWN, "version": UNKNOWN}
    if not path:
        row["runnable"] = False
        return row
    try:
        p = subprocess.run([path, *args], capture_output=True, text=True, timeout=20)
        row["runnable"] = p.returncode == 0
        row["exit_code"] = p.returncode
        # Accept version-looking lines only; failed diagnostics can contain config.
        lines = (p.stdout + "\n" + p.stderr).splitlines()
        version = next((x for x in lines if re.search(r"\d+\.\d+", x) and not re.search(r"token|secret|password|key=|://", x, re.I)), None)
        if version and p.returncode == 0:
            row["version"] = clean(version)
    except (OSError, subprocess.TimeoutExpired) as exc:
        row["probe_error"] = type(exc).__name__
    return row


def frontmatter(path):
    text = path.read_text(errors="replace")
    fields = {}
    if text.startswith("---"):
        body = text.split("---", 2)[1]
        for name in ["name", "description"]:
            m = re.search(r"^" + name + r":\s*(.*)$", body, re.M)
            if m:
                value = m.group(1).strip().strip('"\'')
                if value in ["|", ">", "|-", ">-"]:
                    tail = body[m.end():]
                    value = " ".join(x.strip() for x in tail.splitlines() if x.startswith((" ", "\t")))
                fields[name] = clean(value)
    return fields


def mcp_rows(data, source):
    result = []
    for name, v in data.items():
        if not isinstance(v, dict):
            continue
        cmd = v.get("command")
        args = v.get("args", [])
        enabled = v.get("enabled", not v["disabled"] if isinstance(v.get("disabled"), bool) else UNKNOWN)
        row = {"name": identifier(name), "source": str(source), "purpose": clean(v.get("description", UNKNOWN)),
               "transport": "http" if v.get("url") else "stdio" if cmd else UNKNOWN,
               "endpoint_location": "loopback" if v.get("url") and endpoint(v["url"]).get("host") in ["localhost", "127.0.0.1", "::1"] else "remote_endpoint" if v.get("url") else "local_process" if cmd else UNKNOWN,
               "enabled": enabled if isinstance(enabled, bool) else UNKNOWN,
               "required_program": identifier(Path(cmd).name) if isinstance(cmd, str) else UNKNOWN,
               "program_available": bool(shutil.which(cmd)) if isinstance(cmd, str) else UNKNOWN,
               "argument_count": len(args) if isinstance(args, list) else UNKNOWN,
               "argument_values": "omitted", "package_dependencies": UNKNOWN,
               "environment_variable_names": sorted(identifier(k) for k in v.get("env", {})),
               "header_names": sorted(identifier(k) for k in v.get("headers", v.get("http_headers", {}))),
               "connection_status": "not_tested"}
        if v.get("url"):
            row["endpoint"] = endpoint(v["url"])
        result.append(row)
    return result


def collect(label, home, projects):
    home = Path(home).expanduser()
    codex = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
    warnings, plugins, skills, mcp, configs = [], [], [], [], []
    config_paths = [codex / "config.toml", *codex.glob("*.config.toml")]
    config_paths += [p / ".codex/config.toml" for p in projects]
    plugin_settings = {}
    for path in dict.fromkeys(config_paths):
        if not path.is_file():
            continue
        data = load(path, warnings)
        configs.append({"path": str(path), "top_level_keys": list(data), "values": "omitted"})
        for key, v in data.get("plugins", {}).items():
            state = v.get("enabled", UNKNOWN) if isinstance(v, dict) else UNKNOWN
            plugin_settings.setdefault(str(key), []).append({"config": str(path), "enabled": state})
        mcp.extend(mcp_rows(data.get("mcp_servers", {}), path))
        for v in data.get("skills", {}).get("config", []):
            if isinstance(v, dict):
                skills.append({"name": Path(str(v.get("path", UNKNOWN))).name, "path": str(v.get("path", UNKNOWN)),
                               "enabled": v.get("enabled", UNKNOWN), "kind": "configured_skill", "source": str(path)})
    # These known registry files are read selectively, never copied into reports.
    registry = {}
    for path in [codex / "plugins/installed_plugins.json", codex / "installed_plugins.json"]:
        if not path.is_file():
            continue
        data = load(path, warnings)
        records = data.get("plugins", {})
        if not isinstance(records, dict):
            warnings.append({"path": str(path), "status": "unrecognized_registry_schema"})
            continue
        for name, entries in records.items():
            for entry in entries if isinstance(entries, list) else [entries]:
                if isinstance(entry, dict):
                    registry[str(name)] = entry
    manifests = list((codex / "plugins").rglob(".codex-plugin/plugin.json")) if (codex / "plugins").exists() else []
    for project in projects:
        path = project / ".codex-plugin/plugin.json"
        if path.is_file():
            manifests.append(path)
    roots = []
    seen = set()
    for manifest in manifests:
        meta = load(manifest, warnings)
        root = manifest.parent.parent
        name = str(meta.get("name", root.name))
        keys = [k for k in set(registry) | set(plugin_settings) if k.split("@")[0] == name]
        key = next((k for k in keys if registry.get(k, {}).get("installPath") == str(root)), keys[0] if len(keys) == 1 else name)
        installed = registry.get(key, {}).get("installPath") == str(root)
        settings = plugin_settings.get(key, plugin_settings.get(name, []))
        plugins.append({"name": identifier(name), "description": clean(meta.get("description", UNKNOWN)),
                        "version": clean(meta.get("version", UNKNOWN)), "source": str(manifest),
                        "source_plugin_reference": identifier(key), "source_marketplace": identifier(key.split("@", 1)[1]) if "@" in key else UNKNOWN,
                        "installed": True if installed else UNKNOWN,
                        "evidence": "installation_registry" if installed else "manifest_present_cache_is_not_installation",
                        "configured_states": settings, "enabled": settings[0]["enabled"] if len(settings) == 1 else UNKNOWN,
                        "connection_status": "not_tested"})
        seen.add(key)
        roots.append((root / "skills", "plugin", name))
        path = root / ".mcp.json"
        if path.is_file():
            data = load(path, warnings)
            mcp.extend(mcp_rows(data.get("mcpServers", data), path))
    for key in (set(plugin_settings) | set(registry)) - seen:
        settings = plugin_settings.get(key, [])
        plugins.append({"name": identifier(key.split("@")[0]), "description": UNKNOWN,
                        "source_plugin_reference": identifier(key), "version": clean(registry.get(key, {}).get("version", UNKNOWN)),
                        "installed": True if key in registry else UNKNOWN, "source": "installation_registry" if key in registry else "config_only",
                        "enabled": settings[0]["enabled"] if len(settings) == 1 else UNKNOWN,
                        "configured_states": settings, "connection_status": "not_tested"})
    roots += [(home / ".agents/skills", "custom_or_unattributed", None), (codex / "skills", "custom_or_unattributed", None)]
    for project in projects:
        roots += [(project / ".agents/skills", "custom_or_unattributed", None), (project / ".codex/skills", "custom_or_unattributed", None)]
        for filename in [".mcp.json", ".vscode/mcp.json"]:
            path = project / filename
            if path.is_file():
                data = load(path, warnings)
                mcp.extend(mcp_rows(data.get("mcpServers", data.get("servers", {})), path))
    visited = set()
    for root, kind, plugin in roots:
        if not root.exists():
            continue
        for path in root.rglob("SKILL.md"):
            if path.resolve() in visited:
                continue
            visited.add(path.resolve())
            try:
                meta = frontmatter(path)
                subtype = "bundled" if any(x in path.parts for x in ["builtins", ".system"]) else "cloud_provided_cache" if "remote-skills" in path.parts else kind
                skills.append({"name": meta.get("name", path.parent.name), "description": meta.get("description", UNKNOWN),
                               "path": str(path), "kind": subtype, "source_plugin": plugin or UNKNOWN, "enabled": UNKNOWN,
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "dependency_discovery": "requires_source_review"})
            except OSError as exc:
                warnings.append({"path": str(path), "status": type(exc).__name__})
    definitions = []
    for project in projects:
        for filename in ["package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "pyproject.toml", "uv.lock", "requirements.txt", "Pipfile.lock", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile", "Gemfile.lock", "Brewfile", "Dockerfile", "compose.yaml", ".tool-versions", ".nvmrc", ".python-version"]:
            path = project / filename
            if path.is_file():
                definitions.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "contents": "not_exported"})
    packages = []
    if shutil.which("brew"):
        try:
            env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1")
            p = subprocess.run(["brew", "info", "--json=v2", "--installed"], env=env, capture_output=True, text=True, timeout=45)
            data = json.loads(p.stdout) if p.returncode == 0 else {}
            for group in ["formulae", "casks"]:
                for item in data.get(group, []):
                    packages.append({"manager": "brew", "kind": group, "name": identifier(item.get("full_name", item.get("token", UNKNOWN))),
                                     "versions": [clean(x.get("version", UNKNOWN)) for x in item.get("installed", []) if isinstance(x, dict)] if group == "formulae" else [clean(item.get("version", UNKNOWN))]})
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            warnings.append({"source": "brew", "status": type(exc).__name__})
    cli_plugins = {"status": "not_available", "scope": "Codex CLI installation registry only", "installed": []}
    if shutil.which("codex") and home.resolve() == Path.home().resolve():
        try:
            proc = subprocess.run(["codex", "plugin", "list", "--json"], capture_output=True, text=True, timeout=40)
            data = json.loads(proc.stdout) if proc.returncode == 0 else None
            rows = data.get("installed") if isinstance(data, dict) else None
            if isinstance(rows, list):
                cli_plugins["status"] = "read_success"
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    safe = {k: clean(row[k]) if isinstance(row[k], str) else row[k] for k in ["name", "id", "version", "description", "enabled", "installed"] if isinstance(row.get(k), (str, bool))}
                    cli_plugins["installed"].append(safe)
                    # Preserve structured source/enabled objects as unknown, rather than leaking arbitrary fields.
                    safe.setdefault("enabled", UNKNOWN)
            else:
                cli_plugins["status"] = "unsupported_or_failed"
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            cli_plugins["status"] = type(exc).__name__
    return {"schema_version": 1, "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "environment": {"label": label, "os": platform.system(), "architecture": platform.machine()},
            "coverage": {"scope": "direct_execution_selected_filesystem_roots", "exhaustive_installed_plugin_list": False,
                         "disabled_items": "included_where_configured_or_registered", "account_connections": "not_tested",
                         "cloud_provided_skills": "requires_host_catalog", "unattributed_skills_are_custom": UNKNOWN,
                         "secrets": "not_exported", "configuration_unchanged": True},
            "plugins": plugins, "cli_plugin_registry": cli_plugins, "skills": skills, "mcp_servers": mcp,
            "development_tools": [command_probe(k, v) for k, v in TOOLS.items()],
            "package_managers": packages, "configuration_metadata": configs, "dependency_definitions": definitions,
            "shell_profile_files_present": [str(home / x) for x in [".zshrc", ".zprofile", ".bashrc", ".bash_profile"] if (home / x).is_file()],
            "warnings": warnings}


def write_private(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--label", required=True, choices=["local", "cloud"])
    p.add_argument("--output", required=True)
    p.add_argument("--home", type=Path, default=Path.home())
    p.add_argument("--project", type=Path, action="append", default=[])
    args = p.parse_args()
    data = collect(args.label, args.home, [x.resolve() for x in args.project])
    write_private(args.output, data)
    print(f"Wrote {args.output}; plugins={len(data['plugins'])}, skills={len(data['skills'])}, MCP={len(data['mcp_servers'])}. Coverage is recorded in JSON.")
