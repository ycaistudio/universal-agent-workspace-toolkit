"""The Antigravity pack/restore path stays on its own directories."""

import json
import os
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from toolkit_pack import run_pack  # noqa: E402
from toolkit_restore import cleanup_staging, execute_restore, unpack_and_audit  # noqa: E402
from toolkit_scanner import REDACTED, scan_all_assets  # noqa: E402

TOKEN = "sk-abcdefghijklmnopqrstuvwxyz1234"


class AntigravityRegressionTests(unittest.TestCase):
    def test_scan_pack_restore_ignores_grok_tree(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            ws = root / "ws"
            grok = root / "agent-data"
            (home / ".gemini" / "config" / "skills" / "demo").mkdir(parents=True)
            (home / ".gemini" / "config" / "skills" / "demo" / "SKILL.md").write_text("skill body", encoding="utf-8")
            mcp = home / ".gemini" / "antigravity" / "mcp"
            mcp.mkdir(parents=True)
            (mcp / "server.json").write_text(json.dumps({"env": {"API_KEY": TOKEN}}), encoding="utf-8")
            ws.mkdir()
            (ws / "AGENTS.md").write_text("incoming directive", encoding="utf-8")
            (ws / "note.md").write_text("workspace note", encoding="utf-8")
            (ws / ".env").write_text("SECRET=1", encoding="utf-8")
            (grok / "agents").mkdir(parents=True)
            (grok / "box-secrets.json").write_text("GROK_SHOULD_NOT_BE_PACKED", encoding="utf-8")

            assets = scan_all_assets(home, ws, include_secrets=False)
            self.assertNotIn("Level_6_Memory_Drop", assets)
            self.assertTrue(any(path.name == ".env" for path, _ in assets["excluded"]))
            self.assertEqual(len(assets["Level_1_Agent_Directives"]), 1)
            self.assertTrue(any(path.name == "note.md" for path in assets["Level_4_Workspace_Docs"]))

            result = run_pack(assets, root / "out", home)
            manifest = json.loads(zipfile.ZipFile(result["zip_path"]).read("package_manifest.json"))
            self.assertEqual(manifest["profile"], "antigravity")
            blob = b"".join(zipfile.ZipFile(result["zip_path"]).read(name)
                            for name in zipfile.ZipFile(result["zip_path"]).namelist())
            self.assertNotIn(b"GROK_SHOULD_NOT_BE_PACKED", blob)
            self.assertNotIn(TOKEN.encode(), blob)
            self.assertIn(REDACTED.encode(), blob)

            home2 = root / "home2"
            ws2 = root / "ws2"
            ws2.mkdir()
            (ws2 / "AGENTS.md").write_text("LOCAL", encoding="utf-8")
            (home2 / ".gemini" / "antigravity" / "mcp").mkdir(parents=True)
            (home2 / ".gemini" / "antigravity" / "mcp" / "server.json").write_text('{"keep":true}', encoding="utf-8")
            audit = unpack_and_audit(result["zip_path"])
            try:
                self.assertEqual(audit["corrupted_files"], [])
                restored = execute_restore(
                    audit["staging_dir"], "existing", home2, ws2, src_user="alice", apply_ide=False)
            finally:
                cleanup_staging(audit["staging_dir"])
            self.assertEqual((ws2 / "AGENTS.md").read_text(encoding="utf-8"), "LOCAL")
            self.assertIn("incoming directive", (ws2 / "AGENTS.md.incoming").read_text(encoding="utf-8"))
            self.assertEqual((ws2 / "note.md").read_text(encoding="utf-8"), "workspace note")
            self.assertEqual(
                (home2 / ".gemini" / "antigravity" / "mcp" / "server.json").read_text(encoding="utf-8"),
                '{"keep":true}')
            self.assertTrue((home2 / ".gemini" / "antigravity" / "mcp" / "server.json.incoming").is_file())
            self.assertEqual((home2 / ".gemini" / "config" / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8"),
                             "skill body")
            self.assertIn("skills_dst", restored)

    def test_cli_profile_antigravity_does_not_read_grok_env(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "ws"
            ws.mkdir()
            (ws / "note.md").write_text("antigravity note", encoding="utf-8")
            grok = root / "agent-data"
            (grok / "agents").mkdir(parents=True)
            (grok / "marker.txt").write_text("GROK_MARKER_SHOULD_STAY_OUT", encoding="utf-8")
            env = os.environ.copy()
            env["GROK_AGENT_DATA"] = str(grok)
            env["UAWT_PROFILE"] = "grok"
            proc = subprocess.run(
                [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "pack",
                 "--profile", "antigravity", "-y", "--lang", "en",
                 "--workspace-dir", str(ws), "--output-dir", str(root / "out")],
                cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            zips = list((root / "out").glob("packages/Level_*.zip"))
            self.assertEqual(len(zips), 1)
            manifest = json.loads(zipfile.ZipFile(zips[0]).read("package_manifest.json"))
            self.assertEqual(manifest["profile"], "antigravity")
            names = zipfile.ZipFile(zips[0]).namelist()
            blob = b"".join(zipfile.ZipFile(zips[0]).read(name) for name in names)
            self.assertNotIn(b"GROK_MARKER_SHOULD_STAY_OUT", blob)
            self.assertNotIn("Level_6_Memory_Drop", "\n".join(names))
            self.assertIn("Environment profile: antigravity", proc.stdout)


if __name__ == "__main__":
    unittest.main()
