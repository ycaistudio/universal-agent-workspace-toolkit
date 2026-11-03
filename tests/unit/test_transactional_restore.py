#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit and Failure Injection Tests for Transactional Restore (P0-A / REL-03 / v2.3.1)."""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_restore import RestoreTransaction, execute_restore


class TransactionalRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_restore_tx_test_"))
        self.user_home = self.tmp / "home"
        self.user_home.mkdir(parents=True, exist_ok=True)
        self.target_dir = self.tmp / "workspace"
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.snap_dir = self.tmp / "snapshot"
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir = self.tmp / "staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        # Pre-existing user files
        self.user_existing = self.target_dir / "user_notes.txt"
        self.user_existing.write_text("pre-existing content", encoding="utf-8")

        self.snap_backup = self.snap_dir / "backup_config.json"
        self.snap_backup.write_text('{"version": "original"}', encoding="utf-8")
        self.live_config = self.target_dir / "config.json"
        self.live_config.write_text('{"version": "original"}', encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_transaction_rollback_deletes_new_files_and_restores_modified(self):
        """Baseline REL-03 test: new files removed and snapshot restored."""
        tx = RestoreTransaction(self.snap_dir)

        # 1. New file created by restore
        new_file = self.target_dir / "new_skill.md"
        new_file.write_text("new skill content", encoding="utf-8")
        tx.record_create(new_file)

        # 2. File modified by restore
        self.live_config.write_text('{"version": "corrupted_halfway"}', encoding="utf-8")
        tx.record_modify(self.live_config, self.snap_backup)

        # 3. Trigger rollback
        tx.rollback()

        # Assertions
        self.assertFalse(new_file.exists(), "Newly created file must be deleted upon rollback!")
        self.assertEqual(self.live_config.read_text(encoding="utf-8"), '{"version": "original"}')
        self.assertTrue(self.user_existing.exists())
        self.assertEqual(self.user_existing.read_text(encoding="utf-8"), "pre-existing content")

    def test_fresh_mode_successful_overwrite(self):
        """1. fresh mode successfully overwrites existing files without triggering rollback."""
        docs_dir = self.staging_dir / "Level_4_Workspace_Docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        staged_doc = docs_dir / "doc.txt"
        staged_doc.write_text("NEW_CONTENT_V2", encoding="utf-8")

        target_doc = self.target_dir / "doc.txt"
        target_doc.write_text("OLD_ORIGINAL_CONTENT", encoding="utf-8")

        res = execute_restore(self.staging_dir, "fresh", self.user_home, self.target_dir)
        self.assertEqual(target_doc.read_text(encoding="utf-8"), "NEW_CONTENT_V2")
        self.assertTrue(self.user_existing.exists())
        self.assertEqual(self.user_existing.read_text(encoding="utf-8"), "pre-existing content")

    def test_fresh_mode_second_file_fails_and_first_restores(self):
        """2 & 3. In fresh mode, when file 1 succeeds and file 2 fails, file 1 restores its original content."""
        docs_dir = self.staging_dir / "Level_4_Workspace_Docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "file1.txt").write_text("NEW_1", encoding="utf-8")
        (docs_dir / "file2.txt").write_text("NEW_2", encoding="utf-8")

        target_file1 = self.target_dir / "file1.txt"
        target_file1.write_text("ORIGINAL_1", encoding="utf-8")
        target_file2 = self.target_dir / "file2.txt"
        target_file2.write_text("ORIGINAL_2", encoding="utf-8")

        orig_copy2 = shutil.copy2

        def mock_copy2(src, dst, **kwargs):
            # Inject failure when copying to target file2.txt
            if Path(dst).name == "file2.txt" and "Level_4_Workspace_Docs" in str(src):
                raise OSError("Disk write failure during file2 copy")
            return orig_copy2(src, dst, **kwargs)

        with patch("toolkit_restore.shutil.copy2", side_effect=mock_copy2):
            with self.assertRaises(RuntimeError) as ctx:
                execute_restore(self.staging_dir, "fresh", self.user_home, self.target_dir)
            self.assertIn("Disk write failure", str(ctx.exception))

        # Verification: file 1 was overwritten then restored back to ORIGINAL_1!
        self.assertEqual(target_file1.read_text(encoding="utf-8"), "ORIGINAL_1")
        # Verification: file 2 was never overwritten, remains ORIGINAL_2!
        self.assertEqual(target_file2.read_text(encoding="utf-8"), "ORIGINAL_2")
        # Pre-existing file untouched
        self.assertEqual(self.user_existing.read_text(encoding="utf-8"), "pre-existing content")

    def test_newly_created_files_removed_on_rollback(self):
        """4. Newly created files by restore are completely removed when rollback is triggered."""
        docs_dir = self.staging_dir / "Level_4_Workspace_Docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "brand_new.txt").write_text("BRAND_NEW_DATA", encoding="utf-8")
        (docs_dir / "failing_doc.txt").write_text("FAIL_DATA", encoding="utf-8")

        target_brand_new = self.target_dir / "brand_new.txt"
        self.assertFalse(target_brand_new.exists())

        orig_copy2 = shutil.copy2

        def mock_copy2(src, dst, **kwargs):
            if Path(dst).name == "failing_doc.txt":
                raise PermissionError("Access denied on failing_doc.txt")
            return orig_copy2(src, dst, **kwargs)

        with patch("toolkit_restore.shutil.copy2", side_effect=mock_copy2):
            with self.assertRaises(RuntimeError):
                execute_restore(self.staging_dir, "fresh", self.user_home, self.target_dir)

        # brand_new.txt must NOT exist after rollback
        self.assertFalse(target_brand_new.exists(), "Newly created file must be removed on rollback")
        self.assertEqual(self.user_existing.read_text(encoding="utf-8"), "pre-existing content")

    def test_nonexistent_directories_and_files_handled_on_rollback(self):
        """5. Deeply nested non-existent directories are properly removed if rollback happens."""
        docs_dir = self.staging_dir / "Level_4_Workspace_Docs"
        nested_src = docs_dir / "sub" / "nested" / "deep"
        nested_src.mkdir(parents=True, exist_ok=True)
        (nested_src / "file_a.txt").write_text("A", encoding="utf-8")
        (nested_src / "file_b.txt").write_text("B", encoding="utf-8")

        target_sub = self.target_dir / "sub"
        self.assertFalse(target_sub.exists())

        orig_copy2 = shutil.copy2

        def mock_copy2(src, dst, **kwargs):
            if Path(dst).name == "file_b.txt":
                raise OSError("Simulated write failure on file_b")
            return orig_copy2(src, dst, **kwargs)

        with patch("toolkit_restore.shutil.copy2", side_effect=mock_copy2):
            with self.assertRaises(RuntimeError):
                execute_restore(self.staging_dir, "fresh", self.user_home, self.target_dir)

        # Ensure created directory was cleaned up and not left empty
        self.assertFalse(target_sub.exists(), "Newly created directory tree must be pruned on rollback")

    def test_backup_creation_failure_leaves_original_untouched(self):
        """6. If backup creation fails before overwriting, the original file is NEVER touched."""
        docs_dir = self.staging_dir / "Level_4_Workspace_Docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "target.txt").write_text("ATTEMPTED_OVERWRITE", encoding="utf-8")

        target_file = self.target_dir / "target.txt"
        target_file.write_text("CRITICAL_ORIGINAL_DATA", encoding="utf-8")

        orig_copy2 = shutil.copy2

        def mock_copy2(src, dst, **kwargs):
            # Inject failure when copying to backup location
            if "uawt_restore_tx_backup_" in str(dst) or "_tx_backups" in str(dst):
                raise OSError("Disk full: cannot create backup copy")
            return orig_copy2(src, dst, **kwargs)

        with patch("toolkit_restore.shutil.copy2", side_effect=mock_copy2):
            with self.assertRaises(RuntimeError) as ctx:
                execute_restore(self.staging_dir, "fresh", self.user_home, self.target_dir)
            self.assertIn("Disk full: cannot create backup copy", str(ctx.exception))

        # Crucial invariant: original file is 100% intact!
        self.assertEqual(target_file.read_text(encoding="utf-8"), "CRITICAL_ORIGINAL_DATA")

    def test_rollback_failure_preserves_backup_and_reports_error(self):
        """7. If rollback itself encounters an error, backups are preserved and errors reported."""
        custom_backup_dir = self.tmp / "persisted_backup"
        tx = RestoreTransaction(backup_dir=custom_backup_dir)

        target_file = self.target_dir / "doc_to_mod.txt"
        target_file.write_text("ORIGINAL_BEFORE_MOD", encoding="utf-8")

        # Record modify and overwrite
        tx.backup_and_record_modify(target_file)
        target_file.write_text("MODIFIED_VALUE", encoding="utf-8")

        # Simulate copy2 failure during rollback
        orig_copy2 = shutil.copy2

        def mock_rollback_copy2(src, dst, **kwargs):
            if "doc_to_mod.txt" in str(dst):
                raise PermissionError("Target file locked by another process during rollback")
            return orig_copy2(src, dst, **kwargs)

        with patch("toolkit_restore.shutil.copy2", side_effect=mock_rollback_copy2):
            with self.assertRaises(RuntimeError) as ctx:
                tx.rollback()
            self.assertIn("Rollback encountered errors", str(ctx.exception))
            self.assertIn("Target file locked", str(ctx.exception))

        # Backup directory must be preserved!
        self.assertTrue(custom_backup_dir.exists(), "Backup directory must be kept for manual recovery!")
        # ROLLBACK_ERRORS.txt must exist detailing the situation
        report_file = custom_backup_dir / "ROLLBACK_ERRORS.txt"
        self.assertTrue(report_file.exists(), "Manual recovery report must be written!")
        content = report_file.read_text(encoding="utf-8")
        self.assertIn("Target file locked", content)
        self.assertIn("doc_to_mod.txt", content)


if __name__ == "__main__":
    unittest.main()
