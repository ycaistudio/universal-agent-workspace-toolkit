#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_pack import run_pack


class ConcurrentPackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_concurrent_test_"))
        self.ws = self.tmp / "ws"
        self.ws.mkdir(parents=True, exist_ok=True)
        (self.ws / "AGENTS.md").write_text("Directive content", encoding="utf-8")
        self.out = self.tmp / "out"
        self.out.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unique_tracking_id_and_atomic_packaging(self):
        assets = {
            "include_secrets": False,
            "ws_scan": self.ws,
            "skills_names": [],
            "excluded": [],
            "flagged": [],
            "Level_1_Agent_Directives": [self.ws / "AGENTS.md"],
            "Level_2_System_Settings": [],
            "Level_3_Modular_Skills": [],
            "Level_4_Workspace_Docs": [],
            "Level_5_Heavy_References": [],
            "venvs": []
        }
        res1 = run_pack(assets, self.out, self.tmp)
        res2 = run_pack(assets, self.out, self.tmp)

        # Assert tracking IDs are distinct even if executed in the same second!
        self.assertNotEqual(res1["tracking_id"], res2["tracking_id"])
        self.assertTrue(res1["tracking_id"].startswith("PKG-"))
        self.assertTrue(res2["tracking_id"].startswith("PKG-"))


if __name__ == "__main__":
    unittest.main()
