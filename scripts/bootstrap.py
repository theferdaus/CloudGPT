#!/usr/bin/env python3
"""Install reviewed repository skills without changing configuration or replacing files."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def unsafe_link(path):
    if not path.is_symlink():
        return False
    # macOS has these OS-owned aliases even in a normal temporary directory.
    aliases = {"/var": "/private/var", "/tmp": "/private/tmp", "/etc": "/private/etc"}
    return not (platform.system() == "Darwin" and str(path) in aliases and str(path.resolve()) == aliases[str(path)])


def install(destination, source=ROOT / "skills"):
    destination = Path(destination)
    planned = []
    for skill in sorted(source.iterdir()):
        if skill.is_symlink():
            raise RuntimeError(f"Review source symlink first: {skill}")
        if not skill.is_dir() or not (skill / "SKILL.md").is_file():
            continue
        target_root = destination / skill.name
        # Reject links even if they resolve to matching files; never traverse them.
        for ancestor in [destination, *destination.parents]:
            if unsafe_link(ancestor):
                raise RuntimeError(f"Refusing symlink destination: {ancestor}")
        if target_root.is_symlink():
            raise RuntimeError(f"Refusing symlink destination: {target_root}")
        if target_root.exists() and not target_root.is_dir():
            raise RuntimeError(f"Existing non-directory: {target_root}")
        for existing in target_root.rglob("*") if target_root.exists() else []:
            if existing.is_symlink():
                raise RuntimeError(f"Refusing symlink destination: {existing}")
        for path in skill.rglob("*"):
            if path.is_symlink():
                raise RuntimeError(f"Review source symlink first: {path}")
            if not path.is_file():
                continue
            target = target_root / path.relative_to(skill)
            for parent in [target.parent, *target.parent.parents]:
                if parent.exists() and not parent.is_dir():
                    raise RuntimeError(f"Existing non-directory: {parent}")
            if target.exists():
                if not target.is_file() or target.read_bytes() != path.read_bytes():
                    raise RuntimeError(f"Preserved existing different file: {target}")
            else:
                planned.append((path, target))
    # Preflight all conflicts before the first write.
    for path, target in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(path.read_bytes())
    return [str(target) for _, target in planned]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skills-dir", type=Path, default=ROOT / ".agents/skills")
    args = p.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ required")
    print(json.dumps({"installed_files": install(args.skills_dir), "configuration_changed": False}))
