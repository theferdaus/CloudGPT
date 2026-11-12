#!/usr/bin/env python3
"""On the Mac, export audited skill files privately, retaining divergent copies."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import zipfile

SIGNATURES = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
DENIED = {".env", "auth.json", "credentials.json", "cookies.json", "storage_state.json", "storage-state.json"}


def export(manifest_path, output, selection="all", home=None):
    home = Path(home or Path.home()).resolve()
    manifest = json.loads(Path(manifest_path).read_text())
    fields = ("priority_locally_managed_skills", "priority_files") if selection == "priority" else ("all_locally_managed_skill_directories", "all_locally_managed_files")
    directories = {str(Path(x["directory"])): x for x in manifest[fields[0]]}
    roots = {"codex_user": home / ".codex/skills", "agents_user": home / ".agents/skills", "claude_user": home / ".claude/skills"}
    payloads, records, seen = [], [], set()
    for row in manifest[fields[1]]:
        source = Path(row["path"])
        skill = str(Path(row["skill_path"]).parent)
        meta = directories.get(skill)
        if meta is None or meta.get("scope") not in roots:
            raise ValueError("Unrecognized source skill directory")
        skill_root = Path(skill)
        allowed = roots[meta["scope"]]
        # The manifest is evidence, not permission to read arbitrary personal files.
        if skill_root.parent != allowed or skill_root.is_symlink() or not source.is_relative_to(skill_root):
            raise ValueError("Source path is outside a supported skill root")
        relative = source.relative_to(skill_root)
        if ".." in relative.parts or not source.resolve().is_relative_to(skill_root.resolve()):
            raise ValueError("Source traversal is not allowed")
        for part in [source, *source.parents]:
            if part == allowed.parent:
                break
            if part.is_symlink():
                raise ValueError("Source links require separate review")
        if source.name.casefold() in DENIED or source.name.startswith(".env.") or source.suffix.casefold() in [".pem", ".key", ".p12", ".pfx", ".keychain", ".keychain-db"]:
            raise ValueError("Credential-store-like file requires separate review")
        if row.get("credential_pattern_detected"):
            raise ValueError("Audit flagged a credential pattern; review locally first")
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != row["sha256"] or len(data) != row["bytes"]:
            raise ValueError("A source file changed after the audit; refresh the local audit")
        if SIGNATURES.search(data):
            raise ValueError("A possible credential was found; review locally first")
        if str(relative) != row["relative_path"]:
            raise ValueError("Audited relative path does not match source")
        member = str(PurePosixPath("skills", meta["scope"], skill_root.name, *relative.parts))
        if member in seen:
            raise ValueError("Duplicate archive member")
        seen.add(member)
        payloads.append((member, data))
        records.append({"member": member, "skill": meta["name"], "scope": meta["scope"], "sha256": digest, "bytes": len(data)})
    metadata = {"schema_version": 1, "scope": selection, "credential_stores_included": False, "divergent_copies_preserved": True, "files": records,
                "limitation": "Signature checks do not prove every file is secret-free; the local agent must review before transfer. No source files are changed."}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Do not replace an older transfer or follow an output symlink.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("transfer-manifest.json", json.dumps(metadata, indent=2))
        for member, data in payloads:
            archive.writestr(member, data)
    return {"archive": str(output), "files": len(records), "skill_copies": len({(x["scope"], x["skill"]) for x in records}), "bytes": output.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--selection", choices=["all", "priority"], default="all")
    args = parser.parse_args()
    print(json.dumps(export(args.manifest, args.output, args.selection)))
