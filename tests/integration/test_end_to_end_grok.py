#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
import json
import sqlite3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_grok import scan_grok_assets, run_grok_pack, build_restore_plan, execute_grok_restore
from toolkit_restore import unpack_and_audit, cleanup_staging


class EndToEndGrokTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_e2e_grok_"))
        self.agent_data = self.tmp / "agent-data"
        self.agent_data.mkdir(parents=True, exist_ok=True)
        self.ws = self.tmp / "workspace"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.out = self.tmp / "output"
        self.out.mkdir(parents=True, exist_ok=True)

        # 1. Agent profile & directories
        agent_id = "11111111-2222-3333-4444-555555555555"
        self.agent_dir = self.agent_data / "agents" / agent_id
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        (self.agent_dir / "profile.json").write_text(f'{{"id": "{agent_id}", "name": "TestBot"}}', encoding="utf-8")
        (self.agent_dir / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")

        # 2. Workflows
        wf_dir = self.agent_data / "workflows" / "my_workflow"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "workflow.yaml").write_text("name: test_wf\n", encoding="utf-8")

        # 3. Workspace docs
        (self.ws / "notes.md").write_text("# Grok Project Notes\n", encoding="utf-8")

        # 4. Search index SQLite db
        db_path = self.agent_data / "search-index.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE messages (agent_id TEXT, content TEXT);")
        conn.execute(f"INSERT INTO messages VALUES ('{agent_id}', 'hello world');")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_grok_full_pack_inspect_restore_roundtrip(self):
        # 1. Scan
        paths = {
            "agent_data": self.agent_data,
            "workspace": self.ws,
            "memory_drop": self.ws / "exports" / "memory-drop",
            "cursor_stores": self.tmp / "cursor" / "stores",
            "search_index": self.agent_data / "search-index.db"
        }
        assets = scan_grok_assets(paths)
        self.assertGreater(len(assets["files"]), 0)

        # 2. Pack
        pack_res = run_grok_pack(assets, self.out, self.tmp)
        self.assertTrue(Path(pack_res["zip_path"]).exists())
        self.assertGreater(pack_res["total_files"], 0)

        # 3. Inspect (unpack_and_audit)
        audit = unpack_and_audit(self.out / "packages")
        try:
            self.assertIsNone(audit["error"])
            self.assertGreater(audit["verified_files"], 0)
            self.assertEqual(len(audit["corrupted_files"]), 0)

            # 4. Restore
            target_ws = self.tmp / "target_workspace"
            target_ws.mkdir(parents=True, exist_ok=True)
            target_ad = self.tmp / "target_agent_data"
            target_ad.mkdir(parents=True, exist_ok=True)

            dest_paths = {
                "workspace": target_ws,
                "agent_data": target_ad
            }
            plan = build_restore_plan(audit["staging_dir"], audit["manifest"], dest_paths, "existing", {})
            res = execute_grok_restore(plan, audit["manifest"], self.tmp, dest_paths, {})

            self.assertTrue((target_ws / "notes.md").exists())
            self.assertEqual((target_ws / "notes.md").read_text(encoding="utf-8"), "# Grok Project Notes\n")
            # Sidecar incoming kit check
            incoming_kit = res["incoming_dir"]
            self.assertTrue(incoming_kit.exists())
            self.assertTrue((incoming_kit / "MANUAL_REBUILD.md").exists())
        finally:
            cleanup_staging(audit["staging_dir"])


if __name__ == "__main__":
    unittest.main()
