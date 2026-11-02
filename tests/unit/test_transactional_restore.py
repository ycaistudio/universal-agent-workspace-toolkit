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

from toolkit_restore import RestoreTransaction


class TransactionalRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_restore_tx_test_"))
        self.target_dir = self.tmp / "workspace"
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.snap_dir = self.tmp / "snapshot"
        self.snap_dir.mkdir(parents=True, exist_ok=True)

        # Existing user file that existed before restore
        self.user_existing = self.target_dir / "user_notes.txt"
        self.user_existing.write_text("pre-existing content", encoding="utf-8")

        # Snapshot of a modified file
        self.snap_backup = self.snap_dir / "backup_config.json"
        self.snap_backup.write_text('{"version": "original"}', encoding="utf-8")
        self.live_config = self.target_dir / "config.json"
        self.live_config.write_text('{"version": "original"}', encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_transaction_rollback_deletes_new_files_and_restores_modified(self):
        tx = RestoreTransaction(self.snap_dir)

        # 1. New file created by restore
        new_file = self.target_dir / "new_skill.md"
        new_file.write_text("new skill content", encoding="utf-8")
        tx.record_create(new_file)

        # 2. File modified by restore
        self.live_config.write_text('{"version": "corrupted_halfway"}', encoding="utf-8")
        tx.record_modify(self.live_config, self.snap_backup)

        # 3. Simulate failure and trigger rollback
        tx.rollback()

        # Assert: newly created file is deleted
        self.assertFalse(new_file.exists(), "Newly created file must be deleted upon rollback!")

        # Assert: modified file is restored to original snapshot state
        self.assertEqual(self.live_config.read_text(encoding="utf-8"), '{"version": "original"}')

        # Assert: pre-existing user file is untouched
        self.assertTrue(self.user_existing.exists())
        self.assertEqual(self.user_existing.read_text(encoding="utf-8"), "pre-existing content")


if __name__ == "__main__":
    unittest.main()
