#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
import zipfile
import json
import hashlib
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_restore import unpack_and_audit, cleanup_staging


class LegacyPackageCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_legacy_test_"))
        self.pkg_dir = self.tmp / "packages"
        self.pkg_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_legacy_v220_package_unpacks_and_verifies(self):
        content = b"# Directive in legacy package\n"
        sha = hashlib.sha256(content).hexdigest()
        manifest = {
            "manifest_version": "v2.2.0",
            "profile": "antigravity",
            "tracking_id": "PKG-20261024-120000",
            "created_at": "2026-10-24T12:00:00",
            "file_manifest": {
                "Level_1_Agent_Directives/AGENTS.md": {
                    "size": len(content),
                    "sha256": sha
                }
            }
        }
        zip_path = self.pkg_dir / "Level_1_to_4_Core_Workspace_20261024_120000.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("package_manifest.json", json.dumps(manifest, indent=2))
            z.writestr("Level_1_Agent_Directives/AGENTS.md", content)

        audit = unpack_and_audit(self.pkg_dir)
        try:
            self.assertIsNone(audit["error"])
            self.assertEqual(audit["verified_files"], 1)
            self.assertEqual(len(audit["corrupted_files"]), 0)
        finally:
            cleanup_staging(audit["staging_dir"])


if __name__ == "__main__":
    unittest.main()
