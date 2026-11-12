# Local Codex audit handoff

The cloud chat cannot execute commands on the Mac without a supported local
execution/dispatch tool. Open a local chat in the Mac app and give it this task:

> Audit my local Codex setup first for parity with CloudGPT. Read applicable local
> AGENTS.md instructions. Inspect plugins including disabled entries: names,
> descriptions, source/marketplace, version, installed and enabled state, and
> connection evidence. Inspect bundled, plugin, cloud-provided and custom skills;
> MCP purpose, transport, executables and dependencies; and development tools and
> project dependency definitions. Do not enable, disable or remove anything. Use
> the secret-free collector from theferdaus/CloudGPT after reviewing its source,
> and supplement it with authoritative local app/CLI metadata where available.
> Never export credentials, token values, auth headers, environment values or raw
> config. Keep the inventory JSON and any suitable custom-skill transfer archive
> private and outside GitHub. Report precise coverage and unknowns. Return the
> inventory to the main cloud chat titled “Compare and set up CloudGPT”.

The collector can be run with Python 3.11+ from a reviewed checkout:

```sh
python3 scripts/audit.py --label local --output reports/local.json --project /path/to/workflow
```

If the Mac's Python is older, use an existing Python 3.11+ runtime; do not change
the system Python. No local audit should execute MCP servers or private skill
scripts merely to discover metadata. Separate each service's read-only connection
probe from installation state. A complete audit may need native app settings when
the installation registry is not represented in the filesystem.
