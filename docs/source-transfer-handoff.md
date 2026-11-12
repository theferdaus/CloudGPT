# Return the skill source files

The Mac audit ZIP contains inventory and migration manifests, not skill bodies.
Give the same local Mac Codex chat this follow-up:

> Use the audit you just created to export the **actual source files** for all
> 34 locally managed skill folders listed in
> `custom-skill-migration-manifest.json`. Review the exporter at
> `scripts/export_skill_sources.py` in `theferdaus/CloudGPT` before running it.
> Use its `all` selection. Preserve the differing Codex, Agents and Claude copies
> in separate folders; include their relative scripts, assets and references.
> Review the output for secrets, exclude credentials and authentication stores,
> and return `mac-skill-sources.zip` privately to the main cloud chat. Do not
> change Mac settings or enable anything. Do not publish these private files
> to the public GitHub repository. If hashes changed since the audit, refresh
> the manifest first and report the change.

The exporter itself needs Python 3.11+ and no third-party packages. It neither
starts servers nor executes the skills it packages. It verifies every source
hash, preserves scope/version copies, and rejects unsupported paths and links.
Its signature checks do not replace the local agent's source review.

```sh
python3 scripts/export_skill_sources.py --manifest /path/to/custom-skill-migration-manifest.json --output /private/output/mac-skill-sources.zip
```

The cloud agent can then verify the archive, inspect the real source and its
dependencies, adapt Mac paths, preserve divergent versions, and install the
reviewed portable skills. An inventory alone cannot accomplish those steps.
