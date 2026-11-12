import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit import collect, write_private
from bootstrap import install
from compare import compare


class PortabilityTests(unittest.TestCase):
    def test_disabled_and_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "config.toml").write_text('''[plugins."example@custom"]
enabled = false
[mcp_servers.example]
command = "npx"
args = ["--token", "RAW_ARGUMENT_SECRET"]
enabled = false
url = "https://user:URL_PASSWORD@example.invalid/mcp?token=RAW_QUERY_SECRET"
[mcp_servers.example.env]
API_KEY = "RAW_ENV_SECRET"
[mcp_servers.example.http_headers]
Authorization = "Bearer RAW_HEADER_SECRET"
''')
            (codex / "auth.json").write_text('{"token":"AUTH_FILE_SECRET"}')
            before = (codex / "config.toml").read_bytes()
            with patch.dict(os.environ, {"CODEX_HOME": str(codex)}), patch("audit.shutil.which", return_value=None):
                data = collect("local", home, [])
            serialized = json.dumps(data)
            for secret in ["RAW_ARGUMENT_SECRET", "URL_PASSWORD", "RAW_QUERY_SECRET", "RAW_ENV_SECRET", "RAW_HEADER_SECRET", "AUTH_FILE_SECRET"]:
                self.assertNotIn(secret, serialized)
            self.assertIs(data["plugins"][0]["enabled"], False)
            self.assertIs(data["mcp_servers"][0]["enabled"], False)
            self.assertEqual(data["mcp_servers"][0]["endpoint"]["host"], "example.invalid")
            self.assertEqual((codex / "config.toml").read_bytes(), before)

    def test_cache_is_not_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            codex = home / ".codex"
            path = codex / "plugins/cache/vendor/example/v1/.codex-plugin/plugin.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"name":"example","version":"1.0","description":"Example"}')
            with patch.dict(os.environ, {"CODEX_HOME": str(codex)}), patch("audit.shutil.which", return_value=None):
                data = collect("cloud", home, [])
            self.assertEqual(data["plugins"][0]["installed"], "unknown")

    def test_install_idempotent_conflicts_preflighted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, target = root / "source", root / "target"
            for name in ["a", "z"]:
                (source / name).mkdir(parents=True)
                (source / name / "SKILL.md").write_text(name)
            (target / "z").mkdir(parents=True)
            (target / "z/SKILL.md").write_text("existing-private-skill")
            with self.assertRaises(RuntimeError):
                install(target, source)
            self.assertFalse((target / "a").exists())
            self.assertEqual((target / "z/SKILL.md").read_text(), "existing-private-skill")
            (target / "z/SKILL.md").write_text("z")
            self.assertEqual(len(install(target, source)), 1)
            self.assertEqual(install(target, source), [])

    def test_symlink_and_private_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source/a").mkdir(parents=True)
            (root / "source/a/SKILL.md").write_text("reviewed")
            (root / "other").mkdir()
            (root / "target").symlink_to(root / "other", target_is_directory=True)
            with self.assertRaises(RuntimeError):
                install(root / "target", root / "source")
            out = root / "private.json"
            write_private(out, {"safe": True})
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            link = root / "link.json"
            link.symlink_to(out)
            with self.assertRaises(OSError):
                write_private(link, {"changed": True})
            self.assertEqual(json.loads(out.read_text()), {"safe": True})

    def test_unknown_parity_and_disabled_preserved(self):
        self.assertFalse(compare(None, {})["parity_verified"])
        local = {"plugins": [{"name": "disabled", "enabled": False}], "development_tools": [{"name": "go", "present": True}]}
        cloud = {"development_tools": [{"name": "go", "present": True, "runnable": False}]}
        rows = compare(local, cloud)["items"]
        self.assertEqual([x["status"] for x in rows], ["preserve_disabled", "missing_or_unusable"])


if __name__ == "__main__":
    unittest.main()
