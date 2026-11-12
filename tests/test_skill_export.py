import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_skill_sources import export


class SkillExportTests(unittest.TestCase):
    def fixture(self, root, content=b"---\nname: sample\n---\nSkill body"):
        skill = root / ".codex/skills/sample"
        skill.mkdir(parents=True)
        source = skill / "SKILL.md"
        source.write_bytes(content)
        record = {"path": str(source), "skill_path": str(source), "relative_path": "SKILL.md", "bytes": len(content),
                  "sha256": hashlib.sha256(content).hexdigest(), "credential_pattern_detected": False}
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"all_locally_managed_skill_directories": [{"directory": str(skill), "scope": "codex_user", "name": "sample"}],
                                        "all_locally_managed_files": [record]}))
        return manifest, source

    def test_private_export_keeps_sources_and_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, source = self.fixture(root)
            before = source.read_bytes()
            out = root / "transfer.zip"
            self.assertEqual(export(manifest, out, home=root)["files"], 1)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            with zipfile.ZipFile(out) as archive:
                self.assertEqual(archive.read("skills/codex_user/sample/SKILL.md"), before)
                self.assertNotIn(str(root), archive.read("transfer-manifest.json").decode())

    def test_changed_source_leaves_no_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, source = self.fixture(root)
            source.write_text("changed after audit")
            with self.assertRaises(ValueError):
                export(manifest, root / "transfer.zip", home=root)
            self.assertFalse((root / "transfer.zip").exists())

    def test_credential_signature_blocks_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, _ = self.fixture(root, b"-----BEGIN PRIVATE KEY-----\nFAKE TEST MATERIAL")
            with self.assertRaises(ValueError):
                export(manifest, root / "transfer.zip", home=root)
            self.assertFalse((root / "transfer.zip").exists())

    def test_outside_source_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, source = self.fixture(root)
            data = json.loads(manifest.read_text())
            outside = root / "unrelated.txt"
            outside.write_text("not a skill")
            data["all_locally_managed_files"][0]["path"] = str(outside)
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                export(manifest, root / "transfer.zip", home=root)
            data["all_locally_managed_files"][0]["path"] = str(source)
            manifest.write_text(json.dumps(data))
            source.unlink()
            source.symlink_to(outside)
            with self.assertRaises(ValueError):
                export(manifest, root / "transfer.zip", home=root)

    def test_parent_traversal_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, source = self.fixture(root)
            data = json.loads(manifest.read_text())
            data["all_locally_managed_files"][0]["path"] = str(source.parent / "../../../unrelated.txt")
            data["all_locally_managed_files"][0]["relative_path"] = "../../../unrelated.txt"
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                export(manifest, root / "transfer.zip", home=root)


if __name__ == "__main__":
    unittest.main()
