# CloudGPT capability blueprint

Reproducible, non-destructive tools for auditing a local Codex installation and
comparing it with a cloud executor. This repository is public. Machine inventories,
private custom skills, configuration files and secrets do **not** belong here.

Requires Python 3.11 or later. The collector and installer use only its standard
library. They do not install plugins, change enabled states, copy credentials or
overwrite Codex configuration. Cached plugins are reported separately from proven
installations. Unknown connection state stays unknown.

```sh
python3 scripts/audit.py --label local --output reports/local.json --project /path/to/project
python3 scripts/audit.py --label cloud --output reports/cloud.json --project .
python3 scripts/compare.py --local reports/local.json --cloud reports/cloud.json --output reports/comparison.json
python3 scripts/bootstrap.py --skills-dir /workspace/.agents/skills
python3 scripts/verify.py --output reports/verification.json
python3 -m unittest discover -s tests -v
```

Run the local audit **on the Mac**. A cloud tool list cannot substitute for it.
The collector examines explicit Codex/agent directories and supplied projects;
it does not search every personal file or execute MCP servers or skill scripts.
Pass `--project` for each workflow project. Add authoritative app/plugin metadata
and read-only service checks to the private report separately; filesystem caches
cannot establish account-level installation or OAuth readiness.

The installer deploys only this repository's reviewed custom skill. It fails
before changing anything if a different file exists at the destination. Running
it again with the same files makes no changes. Existing config and disabled
plugins/skills are preserved. Restart or start a new Codex turn if the host needs
to rediscover skills; a file installation is not evidence of agent invocation.

`requirements/runtime.json` defines the baseline and optional workflow checks.
`requirements/smoke.txt` pins the optional browser-test dependency. In an executor
without Playwright, install into a project virtual environment, not system Python:

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements/smoke.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/verify.py --output reports/verification.json
```

The verification exercises Python/SQLite, Node, video encode/decode, document
conversion and browser → API → SQLite → response. Unavailable dependencies are
reported as blocked. These are baseline smoke tests, not proof of parity with
unexamined projects or connected services. Docker is checked separately using a
real daemon query; a client executable alone is insufficient.

## Migrating custom skills and MCP

After comparing real inventories, review each custom skill for Linux paths,
executables, fonts, browser assumptions and package versions. Put only suitable,
secret-free source files under `skills/`; keep private material in private storage.
Declare each dependency in the blueprint before deploying it. Do not copy managed
plugin caches into a custom skill directory or re-enable intentionally disabled
items. `scripts/bootstrap.py` installs all reviewed directories under `skills/`.

For stdio MCP servers, install the pinned server and its executable in the cloud,
then add a server-specific config after reviewing the local entry. For remote MCP,
reuse the service endpoint and perform its supported OAuth or secret binding in
the cloud. Argument values, auth headers, environment values and URL queries are
deliberately omitted from inventories. Configured entries are not tested sessions.

Cloud Environment settings hold secret bindings, allowed domains and reusable
repository setup. GitHub stores this blueprint; the selected cloud executor runs
it. Repository commits alone do not publish a new cloud environment snapshot.

## Platform boundaries

Linux cannot reproduce AppleScript, Shortcuts, macOS Keychain, Finder automation,
Xcode/iOS simulators, Apple-specific signing, local USB/Bluetooth/camera access,
or the Mac's browser session. Keep a Mac runner for those requirements. Cloud
Chromium and the shared Linux desktop provide alternatives for portable browser
and desktop tasks; log in separately when required. A configured VPN is needed
for private devices and LAN services, and does not replace application login.

See [the local handoff](docs/local-handoff.md) for an audit task that a local Codex
chat can execute. Keep exported JSON out of public Git history.

## Detailed Mac audit and portable workflow profile

For the expanded `mac-migration-inventory.json` schema:

```sh
python3 scripts/compare_mac.py --local reports/mac-audit/mac-migration-inventory.json --cloud-filesystem reports/cloud-filesystem-current.json --cloud-host reports/cloud-host-evidence.json --output reports/mac-cloud-comparison.json
sh scripts/setup-portable.sh
python3 scripts/probe_mcp.py
```

The isolated profile pins HyperFrames, Hypit, WaveSpeed MCP, NotebookLM MCP,
faster-whisper and yt-dlp to versions observed in the supplied audit. Its npm
and uv lockfiles pin resolved dependencies. PyAV and CTranslate2 also use the
observed Mac transcription versions because a newer PyAV broke audio decoding.
Project-local caches avoid protected global package directories.

Use `sh /path/to/CloudGPT/scripts/cloud-run.sh <command> ...` to select the pinned
CLI tools and writable model/history caches without editing shell profiles or
replacing HOME. For example, `sh scripts/cloud-run.sh hyperframes --help`.

After reviewing the MCP probes, `scripts/register_cloud_mcp.py` adds a WaveSpeed
entry using only the managed `WAVESPEED_API_KEY` variable name. It stages NotebookLM
disabled until a separate cloud login succeeds. Existing server entries, including
disabled entries, are always preserved. Running it does not refresh an already
running agent's tool catalog or publish environment settings.

The three official skills bundled in the pinned HyperFrames package can be
installed with the non-overwriting installer after reviewing their source:

```sh
python3 scripts/bootstrap.py --source runtimes/media/node_modules/hyperframes/dist/skills --skills-dir /workspace/.agents/skills
```

They are portable alternatives, not verified copies of the Mac's divergent skill
versions. Do not replace user-specific skills with them.

## Transfer the actual Mac skill sources

The audit ZIP contains paths and hashes, not skill bodies. On the Mac, review the
exporter and source files, then run:

```sh
python3 scripts/export_skill_sources.py --manifest /path/to/custom-skill-migration-manifest.json --output /private/output/mac-skill-sources.zip
```

It reads only the audited `.codex/skills`, `.agents/skills` and `.claude/skills`
files, verifies each hash, keeps scope/version copies separate, rejects links
and credential-store-like files, and screens common credential signatures.
The local agent must still review the bundle for secrets. Source files remain
unchanged, and no data is uploaded. Transfer this ZIP privately to the cloud
audit chat. Keep the bundle and private skills outside this public repository.
