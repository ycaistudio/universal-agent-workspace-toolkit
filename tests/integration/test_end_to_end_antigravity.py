#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_scanner import scan_all_assets
from toolkit_pack import run_pack
from toolkit_restore import unpack_and_audit, cleanup_staging, execute_restore


class EndToEndAntigravityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_e2e_anti_"))
        self.user_home = self.tmp / "user_home"
        self.user_home.mkdir(parents=True, exist_ok=True)
        self.ws = self.user_home / "Workspace"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.out = self.tmp / "output"
        self.out.mkdir(parents=True, exist_ok=True)

        # Create realistic Antigravity assets
        (self.ws / "AGENTS.md").write_text("# Master Agent Directive\n", encoding="utf-8")
        (self.ws / "project_notes.md").write_text("# Project Notes\n", encoding="utf-8")

        # Mock skill
        skill_dir = self.user_home / ".gemini" / "config" / "skills" / "demo-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\n# Demo\n", encoding="utf-8")

        # Mock MCP
        mcp_dir = self.user_home / ".gemini" / "antigravity" / "mcp" / "demo_mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        (mcp_dir / "server.json").write_text('{"name": "demo"}', encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_antigravity_full_pack_inspect_restore_roundtrip(self):
        # 1. Scan
        assets = scan_all_assets(self.user_home, custom_ws=self.ws)
        l1_resolved = [p.resolve() for p in assets["Level_1_Agent_Directives"]]
        self.assertIn((self.ws / "AGENTS.md").resolve(), l1_resolved)
        self.assertEqual(len(assets["skills_names"]), 1)

        # 2. Pack
        pack_res = run_pack(assets, self.out, self.user_home)
        self.assertTrue(Path(pack_res["zip_path"]).exists())
        self.assertGreaterEqual(pack_res["total_files"], 4)

        # 3. Inspect (unpack_and_audit)
        audit = unpack_and_audit(self.out / "packages")
        try:
            self.assertIsNone(audit["error"])
            self.assertEqual(audit["verified_files"], pack_res["total_files"])
            self.assertEqual(len(audit["corrupted_files"]), 0)

            # 4. Restore into fresh target
            target_ws = self.tmp / "restored_workspace"
            target_ws.mkdir(parents=True, exist_ok=True)
            restore_res = execute_restore(audit["staging_dir"], "fresh", self.user_home, target_ws)
            self.assertTrue((target_ws / "AGENTS.md").exists())
            self.assertTrue((target_ws / "project_notes.md").exists())
            self.assertEqual((target_ws / "AGENTS.md").read_text(encoding="utf-8"), "# Master Agent Directive\n")
        finally:
            cleanup_staging(audit["staging_dir"])


if __name__ == "__main__":
    unittest.main()
