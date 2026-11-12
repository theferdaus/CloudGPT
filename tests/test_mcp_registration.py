from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from register_cloud_mcp import register


class RegistrationTests(unittest.TestCase):
    def test_existing_disabled_server_and_config_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config.toml"
            before = '# Existing user preference\nmodel = "existing"\n[mcp_servers.wavespeed]\nenabled = false\ncommand = "existing"\n'
            config.write_text(before)
            result = register(config, root)
            self.assertEqual(result["added"], ["notebooklm"])
            self.assertTrue(config.read_text().startswith(before))
            parsed = tomllib.loads(config.read_text())
            self.assertFalse(parsed["mcp_servers"]["wavespeed"]["enabled"])
            self.assertEqual(parsed["mcp_servers"]["wavespeed"]["command"], "existing")
            self.assertFalse(parsed["mcp_servers"]["notebooklm"]["enabled"])
            self.assertFalse(register(config, root)["changed"])

    def test_only_secret_binding_name_written(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config.toml"
            result = register(config, root)
            self.assertEqual(result["added"], ["wavespeed", "notebooklm"])
            parsed = tomllib.loads(config.read_text())
            self.assertEqual(parsed["mcp_servers"]["wavespeed"]["env_vars"], ["WAVESPEED_API_KEY"])
            self.assertFalse(result["credential_values_written"])


if __name__ == "__main__":
    unittest.main()
