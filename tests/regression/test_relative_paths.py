#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
import zipfile
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_pack import run_pack
from toolkit_restore import execute_restore, _staged_files


class RelativePathPreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_rel_test_"))
        self.ws = self.tmp / "workspace"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.out = self.tmp / "output"
        self.out.mkdir(parents=True, exist_ok=True)

        # 1. Root directive
        self.root_agent = self.ws / "AGENTS.md"
        self.root_agent.write_text("Root agent directive", encoding="utf-8")

        # 2. Nested directive in subproject
        self.sub_dir = self.ws / "subproject" / "nested"
        self.sub_dir.mkdir(parents=True, exist_ok=True)
        self.nested_agent = self.sub_dir / "AGENTS.md"
        self.nested_agent.write_text("Nested subproject directive", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nested_directives_preserve_relative_paths_no_flattening(self):
        assets = {
            "include_secrets": False,
            "ws_scan": self.ws,
            "skills_names": [],
            "excluded": [],
            "flagged": [],
            "Level_1_Agent_Directives": [self.root_agent, self.nested_agent],
            "Level_2_System_Settings": [],
            "Level_3_Modular_Skills": [],
            "Level_4_Workspace_Docs": [],
            "Level_5_Heavy_References": [],
            "venvs": []
        }
        res = run_pack(assets, self.out, self.tmp)
        zip_path = Path(res["zip_path"])

        # Inspect zip contents
        with zipfile.ZipFile(zip_path, "r") as z:
            namelist = z.namelist()
            # Root directive
            self.assertIn("Level_1_Agent_Directives/AGENTS.md", namelist)
            # Nested directive must NOT be flattened to Level_1_Agent_Directives/AGENTS.md!
            nested_entry = "Level_1_Agent_Directives/subproject/nested/AGENTS.md"
            self.assertIn(nested_entry, namelist, "Nested AGENTS.md must preserve relative path!")

    def test_legacy_flat_package_backward_compatibility(self):
        """A legacy flat package with Level_1_Agent_Directives/AGENTS.md restores to workspace root."""
        staging = self.tmp / "legacy_staging"
        l1 = staging / "Level_1_Agent_Directives"
        l1.mkdir(parents=True, exist_ok=True)
        (l1 / "AGENTS.md").write_text("Legacy flat directive", encoding="utf-8")

        ws_target = self.tmp / "restored_ws"
        ws_target.mkdir(parents=True, exist_ok=True)
        res = execute_restore(staging, "fresh", self.tmp, ws_target)

        restored_agent = ws_target / "AGENTS.md"
        self.assertTrue(restored_agent.exists())
        self.assertEqual(restored_agent.read_text(encoding="utf-8"), "Legacy flat directive")


if __name__ == "__main__":
    unittest.main()
