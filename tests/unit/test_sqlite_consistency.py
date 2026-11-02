#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
import sqlite3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_grok import _snapshot_sqlite


class SqliteConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_sqlite_test_"))
        self.db_src = self.tmp / "test.db"
        conn = sqlite3.connect(self.db_src)
        conn.execute("CREATE TABLE items (id INT, val TEXT);")
        conn.execute("INSERT INTO items VALUES (1, 'hello'), (2, 'world');")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sqlite_snapshot_success(self):
        dest = self.tmp / "snapshot.db"
        ok, consistent, err = _snapshot_sqlite(self.db_src, dest, allow_raw_copy=False)
        self.assertTrue(ok)
        self.assertTrue(consistent)
        self.assertEqual(err, "")
        self.assertTrue(dest.exists())

        # Verify data in destination snapshot
        conn = sqlite3.connect(dest)
        rows = conn.execute("SELECT * FROM items").fetchall()
        conn.close()
        self.assertEqual(len(rows), 2)

    def test_sqlite_snapshot_failure_disallows_raw_copy_by_default(self):
        fake_db = self.tmp / "corrupted.db"
        fake_db.write_text("not a real sqlite database header", encoding="utf-8")
        dest = self.tmp / "should_not_exist.db"
        ok, consistent, err = _snapshot_sqlite(fake_db, dest, allow_raw_copy=False)
        self.assertFalse(ok)
        self.assertFalse(consistent)
        self.assertFalse(dest.exists(), "Corrupted database must not be raw-copied when allow_raw_copy=False!")


if __name__ == "__main__":
    unittest.main()
