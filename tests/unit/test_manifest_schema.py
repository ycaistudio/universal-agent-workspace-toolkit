#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_restore import validate_manifest_schema


class ManifestSchemaTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        manifest = {
            "manifest_version": "v2.3.0",
            "profile": "antigravity",
            "tracking_id": "PKG-20261103-080000-abcd1234",
            "created_at": "2026-11-03T08:00:00",
            "file_manifest": {
                "Level_1_Agent_Directives/AGENTS.md": {
                    "size": 1024,
                    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                }
            }
        }
        valid, errors = validate_manifest_schema(manifest)
        self.assertTrue(valid)
        self.assertEqual(len(errors), 0)

    def test_missing_required_fields_fails(self):
        incomplete = {
            "manifest_version": "v2.3.0",
            "profile": "antigravity"
        }
        valid, errors = validate_manifest_schema(incomplete)
        self.assertFalse(valid)
        self.assertTrue(any("tracking_id" in err for err in errors))
        self.assertTrue(any("file_manifest" in err for err in errors))

    def test_invalid_sha256_format_fails(self):
        bad_sha = {
            "manifest_version": "v2.3.0",
            "profile": "antigravity",
            "tracking_id": "PKG-20261103-080000-abcd1234",
            "created_at": "2026-11-03T08:00:00",
            "file_manifest": {
                "Level_1_Agent_Directives/AGENTS.md": {
                    "size": 100,
                    "sha256": "invalid_short_hash"
                }
            }
        }
        valid, errors = validate_manifest_schema(bad_sha)
        self.assertFalse(valid)
        self.assertTrue(any("sha256" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
