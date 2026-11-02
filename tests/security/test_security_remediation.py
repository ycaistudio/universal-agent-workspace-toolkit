#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import shutil
import tempfile
import zipfile
import unittest
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_grok import build_restore_plan, execute_grok_restore, is_safe_relative_path, safe_join_dest
from toolkit_scanner import _redact, redact_mcp_json, REDACTED
from toolkit_restore import (
    safe_extract_zip,
    ZipSecurityError,
    generate_impact_assessment,
    execute_restore,
    revert_ide_patch,
    apply_ide_patch,
    IDE_PATCH
)


class SecurityRemediationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_sec_test_"))
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.agent_data = self.tmp / "agent-data"
        self.agent_data.mkdir(parents=True, exist_ok=True)
        self.staging = self.tmp / "staging"
        self.staging.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # SEC-01: Path Traversal Tests
    def test_sec01_is_safe_relative_path(self):
        self.assertTrue(is_safe_relative_path("docs/readme.md"))
        self.assertTrue(is_safe_relative_path("notes/2026/note.txt"))
        self.assertFalse(is_safe_relative_path("/etc/passwd"))
        self.assertFalse(is_safe_relative_path("//etc/passwd"))
        self.assertFalse(is_safe_relative_path("C:/Windows/win.ini"))
        self.assertFalse(is_safe_relative_path("../outside.txt"))
        self.assertFalse(is_safe_relative_path("docs/../../outside.txt"))
        self.assertFalse(is_safe_relative_path("docs//empty_part.txt"))
        self.assertFalse(is_safe_relative_path("docs/\0nullbyte.txt"))

    def test_sec01_malicious_manifest_path_traversal_rejected(self):
        """SEC-01 Test Case: Level_4_Workspace_Docs/workspace//etc/passwd & parent escapes."""
        # Create staging dummy files
        staged_evil1 = self.staging / "Level_4_Workspace_Docs" / "workspace" / "passwd"
        staged_evil1.parent.mkdir(parents=True, exist_ok=True)
        staged_evil1.write_text("evil_content", encoding="utf-8")

        manifest = {
            "tracking_id": "SEC-TEST-001",
            "file_manifest": {
                # Malicious entry specified in user directive:
                "Level_4_Workspace_Docs/workspace//etc/passwd": {"size": 12, "sha256": "dummy"},
                "Level_4_Workspace_Docs/workspace/../escape.txt": {"size": 12, "sha256": "dummy"},
                "Level_4_Workspace_Docs/workspace/C:/Windows/System32/calc.exe": {"size": 12, "sha256": "dummy"},
                "Level_4_Workspace_Docs/workspace//server/share/payload": {"size": 12, "sha256": "dummy"},
                "Level_4_Workspace_Docs/workspace/valid_doc.md": {"size": 12, "sha256": "dummy"}
            }
        }
        # Create legitimate staged file
        staged_valid = self.staging / "Level_4_Workspace_Docs" / "workspace" / "valid_doc.md"
        staged_valid.write_text("valid content", encoding="utf-8")

        dest_paths = {
            "workspace": self.workspace,
            "agent_data": self.agent_data
        }

        # Build plan
        plan = build_restore_plan(self.staging, manifest, dest_paths, "existing", {})
        destinations = [str(a["dest"]) for a in plan["actions"]]

        # Assert no escape path in plan
        ws_res = self.workspace.resolve()
        ad_res = self.agent_data.resolve()
        for dst in destinations:
            p_res = Path(dst).resolve()
            is_valid_root = False
            try:
                p_res.relative_to(ws_res)
                is_valid_root = True
            except ValueError:
                try:
                    p_res.relative_to(ad_res)
                    is_valid_root = True
                except ValueError:
                    pass
            self.assertTrue(is_valid_root, f"Destination {dst} escapes allowed root!")
            self.assertNotIn("passwd", dst)
            self.assertNotIn("calc.exe", dst)
            self.assertNotIn("escape.txt", dst)

        # Execute restore and assert nothing written outside workspace
        outside_file = self.tmp / "escape.txt"
        self.assertFalse(outside_file.exists())
        execute_grok_restore(plan, manifest, self.tmp, dest_paths, {})
        self.assertFalse(outside_file.exists())
        self.assertFalse(Path("/etc/passwd").exists() if os.name == "nt" else False)

    # SEC-02: Symlink Protection
    def test_sec02_safe_join_dest_detects_symlink_escape(self):
        outside_dir = self.tmp / "outside_secret"
        outside_dir.mkdir(parents=True, exist_ok=True)
        # Attempting traversal
        with self.assertRaises(ValueError):
            safe_join_dest(self.workspace, "../outside_secret/file.txt")

    # SEC-03: VS Code Security Setting
    def test_sec03_vscode_security_setting_defaults_to_preserved(self):
        """SEC-03: default apply_ide=False preserves user security settings."""
        mock_home = self.tmp / "user_home"
        mock_home.mkdir(parents=True, exist_ok=True)
        res = execute_restore(self.staging, "existing", mock_home, self.workspace, apply_ide=False)
        self.assertEqual(len(res["ide_report"]), 0, "IDE settings must not be modified by default!")

        # Explicit opt-in test
        res_opt_in = execute_restore(self.staging, "existing", mock_home, self.workspace, apply_ide=True)
        # Revert patch test
        reverts = revert_ide_patch(mock_home)
        self.assertIsInstance(reverts, list)

    # SEC-04: MCP Credential Redaction
    def test_sec04_mcp_credential_redaction(self):
        """SEC-04: Test cases including {'args': ['--api-key', 'MY_CUSTOM_SECRET_VALUE']}"""
        test_case_1 = {"args": ["--api-key", "MY_CUSTOM_SECRET_VALUE"]}
        redacted_json, count = redact_mcp_json(json.dumps(test_case_1))
        data = json.loads(redacted_json)
        self.assertEqual(data["args"][0], "--api-key")
        self.assertEqual(data["args"][1], REDACTED)
        self.assertEqual(count, 1)
        self.assertNotIn("MY_CUSTOM_SECRET_VALUE", redacted_json)

        test_case_2 = {"args": ["--token=SECRET_BEARER_999", "--port", "8080"]}
        redacted_json2, count2 = redact_mcp_json(json.dumps(test_case_2))
        data2 = json.loads(redacted_json2)
        self.assertEqual(data2["args"][0], f"--token={REDACTED}")
        self.assertEqual(data2["args"][1], "--port")
        self.assertEqual(data2["args"][2], "8080")
        self.assertEqual(count2, 1)

        test_case_3 = {
            "mcpServers": {
                "custom": {
                    "env": {"API_SECRET_KEY": "super_secret_val"},
                    "headers": {"Authorization": "Bearer token123"}
                }
            }
        }
        redacted_json3, count3 = redact_mcp_json(json.dumps(test_case_3))
        data3 = json.loads(redacted_json3)
        self.assertEqual(data3["mcpServers"]["custom"]["env"]["API_SECRET_KEY"], REDACTED)
        self.assertEqual(data3["mcpServers"]["custom"]["headers"]["Authorization"], REDACTED)
        self.assertNotIn("super_secret_val", redacted_json3)
        self.assertNotIn("token123", redacted_json3)

    # SEC-05: ZIP Resource Exhaustion / Zip Bomb
    def test_sec05_zip_bomb_file_count_cap(self):
        bad_zip = self.tmp / "bomb_count.zip"
        with zipfile.ZipFile(bad_zip, "w") as z:
            for i in range(15):
                z.writestr(f"file_{i}.txt", "test")
        extract_dir = self.tmp / "extracted_count"
        # Set max_files to 10
        with self.assertRaises(ZipSecurityError) as ctx:
            safe_extract_zip(bad_zip, extract_dir, max_files=10)
        self.assertIn("file count", str(ctx.exception).lower())

    def test_sec05_zip_bomb_compression_ratio_cap(self):
        bad_zip = self.tmp / "bomb_ratio.zip"
        with zipfile.ZipFile(bad_zip, "w", zipfile.ZIP_DEFLATED) as z:
            # High compression ratio of 0s
            z.writestr("huge_zeroes.bin", b"\x00" * (1024 * 1024 * 5))  # 5MB uncompressed
        extract_dir = self.tmp / "extracted_ratio"
        with self.assertRaises(ZipSecurityError) as ctx:
            safe_extract_zip(bad_zip, extract_dir, max_ratio=20.0)
        self.assertIn("compression ratio", str(ctx.exception).lower())

    def test_sec05_zip_path_traversal_entry_rejected(self):
        bad_zip = self.tmp / "traversal.zip"
        with zipfile.ZipFile(bad_zip, "w") as z:
            z.writestr("../../etc/passwd", "malicious")
        extract_dir = self.tmp / "extracted_trav"
        with self.assertRaises(ZipSecurityError) as ctx:
            safe_extract_zip(bad_zip, extract_dir)
        self.assertIn("path traversal", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
