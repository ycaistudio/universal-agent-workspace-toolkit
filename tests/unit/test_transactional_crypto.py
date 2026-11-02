#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
import zipfile
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit_crypto import encrypt_packages, decrypt_package, EncryptionError


class TransactionalEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_crypto_test_"))
        self.part1 = self.tmp / "test_part_01.zip"
        self.part2 = self.tmp / "test_part_02.zip"
        with zipfile.ZipFile(self.part1, "w") as z:
            z.writestr("test1.txt", "data 1")
        with zipfile.ZipFile(self.part2, "w") as z:
            z.writestr("test2.txt", "data 2")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transactional_encryption_success(self):
        try:
            enc_paths = encrypt_packages([self.part1, self.part2], "SecretPassphrase123!")
            self.assertEqual(len(enc_paths), 2)
            self.assertTrue(enc_paths[0].exists())
            self.assertTrue(enc_paths[1].exists())
            self.assertFalse(self.part1.exists(), "Plaintext part1 must be removed after successful encryption")
            self.assertFalse(self.part2.exists(), "Plaintext part2 must be removed after successful encryption")
        except EncryptionError as e:
            # If openssl is not installed in the test environment, skip gracefully
            if "openssl" in str(e).lower() or "not found" in str(e).lower():
                self.skipTest("OpenSSL not available on test machine")
            else:
                raise

    def test_transactional_encryption_failure_rollback(self):
        """Simulates failure on part 2: asserts part 1 plaintext is NOT deleted."""
        # Corrupt part2 by making it a directory or unreadable
        corrupt_part = self.tmp / "non_existent_part.zip"
        try:
            with self.assertRaises(EncryptionError):
                encrypt_packages([self.part1, corrupt_part], "SecretPassphrase123!")
            # Assert part1 plaintext is preserved!
            self.assertTrue(self.part1.exists(), "Plaintext part1 must be preserved when part2 fails!")
            # Assert no partial .enc is left
            enc1 = Path(str(self.part1) + ".enc")
            self.assertFalse(enc1.exists(), "Partial .enc must not exist after failure!")
        except EncryptionError as e:
            if "openssl" in str(e).lower():
                self.skipTest("OpenSSL not available on test machine")


if __name__ == "__main__":
    unittest.main()
