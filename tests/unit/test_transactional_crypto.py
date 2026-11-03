#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit and Failure Injection Tests for Transactional Multi-Part Encryption (P0-B / REL-02 / v2.3.1)."""

import os
import sys
import shutil
import tempfile
import zipfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import toolkit_crypto
from toolkit_crypto import (
    encrypt_packages,
    encrypt_package,
    decrypt_package,
    EncryptionError,
    openssl_path,
)


def _setup_mock_openssl_if_needed():
    """If OpenSSL CLI is not available on the test machine, provide a reliable mock cipher

    so that staging, verification, multi-part commit, failure injection, and rollback logic
    can be 100% verified across all platforms.
    """
    if openssl_path() is not None:
        return None, None

    def mock_run_openssl(src, dst, passphrase, decrypt=False):
        src_path = Path(src)
        dst_path = Path(dst)
        if not decrypt:
            raw = src_path.read_bytes()
            dst_path.write_bytes(b"MOCK_CIPHER:" + raw)
        else:
            raw = src_path.read_bytes()
            prefix = b"MOCK_CIPHER:"
            if raw.startswith(prefix):
                dst_path.write_bytes(raw[len(prefix):])
            else:
                dst_path.write_bytes(raw)
        return dst_path

    return "/usr/bin/mock_openssl", mock_run_openssl


class TransactionalEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uawt_crypto_test_"))
        self.part1 = self.tmp / "test_part_01.zip"
        self.part2 = self.tmp / "test_part_02.zip"
        self.part3 = self.tmp / "test_part_03.zip"

        with zipfile.ZipFile(self.part1, "w") as z:
            z.writestr("test1.txt", "data 1")
        with zipfile.ZipFile(self.part2, "w") as z:
            z.writestr("test2.txt", "data 2")
        with zipfile.ZipFile(self.part3, "w") as z:
            z.writestr("test3.txt", "data 3")

        self.passphrase = "SecretPassphrase123!"

        mock_bin, self.mock_cipher = _setup_mock_openssl_if_needed()
        self.mock_bin = mock_bin
        self.patches = []
        if self.mock_bin:
            p1 = patch("toolkit_crypto.openssl_path", return_value=self.mock_bin)
            p2 = patch("toolkit_crypto._run_openssl", side_effect=self.mock_cipher)
            self.patches.extend([p1, p2])
            for p in self.patches:
                p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_all_parts_successful_encryption(self):
        """1. All parts successfully encrypt: all .enc exist and plaintext zips removed."""
        enc_paths = encrypt_packages([self.part1, self.part2, self.part3], self.passphrase)
        self.assertEqual(len(enc_paths), 3)
        for ep in enc_paths:
            self.assertTrue(ep.exists(), f"Encrypted file {ep} must exist")
        self.assertFalse(self.part1.exists(), "Plaintext part1 must be removed after successful commit")
        self.assertFalse(self.part2.exists(), "Plaintext part2 must be removed after successful commit")
        self.assertFalse(self.part3.exists(), "Plaintext part3 must be removed after successful commit")

    def test_02_first_part_commit_failure(self):
        """2. First part commit failure: all original plaintext ZIPs remain intact."""
        orig_commit = toolkit_crypto._commit_file

        def mock_commit(src, dst):
            if "test_part_01.zip.enc" in str(dst):
                raise OSError("Simulated disk error on part 1 commit")
            return orig_commit(src, dst)

        with patch("toolkit_crypto._commit_file", side_effect=mock_commit):
            with self.assertRaises(EncryptionError) as ctx:
                encrypt_packages([self.part1, self.part2, self.part3], self.passphrase)
            self.assertIn("Multi-part encryption commit failed", str(ctx.exception))
            self.assertIn("Simulated disk error on part 1 commit", str(ctx.exception))

        # Invariant: all 3 plaintext ZIPs preserved!
        self.assertTrue(self.part1.exists(), "Part 1 plaintext must be preserved!")
        self.assertTrue(self.part2.exists(), "Part 2 plaintext must be preserved!")
        self.assertTrue(self.part3.exists(), "Part 3 plaintext must be preserved!")
        self.assertFalse(Path(str(self.part1) + ".enc").exists())

    def test_03_second_part_commit_failure(self):
        """3. Second part commit failure: part 1 .enc rolled back, all plaintext ZIPs intact."""
        orig_commit = toolkit_crypto._commit_file

        def mock_commit(src, dst):
            if "test_part_02.zip.enc" in str(dst):
                raise PermissionError("Part 2 locked by antivirus on commit")
            return orig_commit(src, dst)

        with patch("toolkit_crypto._commit_file", side_effect=mock_commit):
            with self.assertRaises(EncryptionError) as ctx:
                encrypt_packages([self.part1, self.part2, self.part3], self.passphrase)
            self.assertIn("Part 2 locked by antivirus on commit", str(ctx.exception))

        # Verification: part 1 .enc was rolled back!
        enc1 = Path(str(self.part1) + ".enc")
        enc2 = Path(str(self.part2) + ".enc")
        enc3 = Path(str(self.part3) + ".enc")
        self.assertFalse(enc1.exists(), "Committed part 1 must be unlinked during rollback!")
        self.assertFalse(enc2.exists())
        self.assertFalse(enc3.exists())

        # Invariant: all plaintext files preserved!
        self.assertTrue(self.part1.exists(), "Part 1 plaintext must remain!")
        self.assertTrue(self.part2.exists(), "Part 2 plaintext must remain!")
        self.assertTrue(self.part3.exists(), "Part 3 plaintext must remain!")

    def test_04_last_part_commit_failure(self):
        """4. Last part commit failure: part 1 & 2 .enc rolled back, all plaintext ZIPs intact."""
        orig_commit = toolkit_crypto._commit_file

        def mock_commit(src, dst):
            if "test_part_03.zip.enc" in str(dst):
                raise OSError("Cross-device link failure on part 3")
            return orig_commit(src, dst)

        with patch("toolkit_crypto._commit_file", side_effect=mock_commit):
            with self.assertRaises(EncryptionError) as ctx:
                encrypt_packages([self.part1, self.part2, self.part3], self.passphrase)
            self.assertIn("Cross-device link failure on part 3", str(ctx.exception))

        self.assertFalse(Path(str(self.part1) + ".enc").exists(), "Part 1 must be rolled back")
        self.assertFalse(Path(str(self.part2) + ".enc").exists(), "Part 2 must be rolled back")
        self.assertFalse(Path(str(self.part3) + ".enc").exists())
        self.assertTrue(self.part1.exists())
        self.assertTrue(self.part2.exists())
        self.assertTrue(self.part3.exists())

    def test_05_encryption_verification_failure(self):
        """5. Encryption verification failure during staging: clean abort, no files committed."""
        with patch("toolkit_crypto.decrypt_package", side_effect=EncryptionError("HMAC corrupt")):
            with self.assertRaises(EncryptionError) as ctx:
                encrypt_packages([self.part1, self.part2], self.passphrase)
            self.assertIn("Staging/verification failed", str(ctx.exception))

        self.assertTrue(self.part1.exists())
        self.assertTrue(self.part2.exists())
        self.assertFalse(Path(str(self.part1) + ".enc").exists())
        self.assertFalse(Path(str(self.part2) + ".enc").exists())

    def test_06_target_already_exists_aborts_without_modifications(self):
        """6. Target .enc already exists beforehand: abort immediately, leave target intact."""
        pre_existing_enc = Path(str(self.part1) + ".enc")
        pre_existing_enc.write_text("PRE_EXISTING_ENCRYPTED_DATA", encoding="utf-8")

        with self.assertRaises(EncryptionError) as ctx:
            encrypt_packages([self.part1, self.part2], self.passphrase)
        self.assertIn("already exists", str(ctx.exception))

        # Pre-existing file content untouched
        self.assertEqual(pre_existing_enc.read_text(encoding="utf-8"), "PRE_EXISTING_ENCRYPTED_DATA")
        # All plaintext zips untouched
        self.assertTrue(self.part1.exists())
        self.assertTrue(self.part2.exists())

    def test_07_commit_failure_preserves_all_original_zips(self):
        """7. Explicit verification that plaintext ZIP unlinking is NEVER called on commit failure."""
        unlinked_zips = []
        orig_unlink = Path.unlink

        def tracking_unlink(path_obj, missing_ok=False):
            if str(path_obj).endswith(".zip"):
                unlinked_zips.append(str(path_obj))
            return orig_unlink(path_obj, missing_ok=missing_ok)

        def failing_commit(src, dst):
            if "test_part_02.zip.enc" in str(dst):
                raise OSError("Commit disk write error")
            return orig_replace(src, dst)

        orig_replace = os.replace
        with patch("toolkit_crypto._commit_file", side_effect=failing_commit):
            with patch.object(Path, "unlink", side_effect=tracking_unlink):
                with self.assertRaises(EncryptionError):
                    encrypt_packages([self.part1, self.part2], self.passphrase)

        self.assertEqual(len(unlinked_zips), 0, "No plaintext ZIP must be unlinked when commit fails!")
        self.assertTrue(self.part1.exists())
        self.assertTrue(self.part2.exists())

    def test_08_no_unidentified_partial_enc_files_left(self):
        """8. No temporary *.enc_tmp_* or *.cipher_tmp_* files are left behind on failure."""
        def failing_commit(src, dst):
            raise OSError("Immediate failure")

        with patch("toolkit_crypto._commit_file", side_effect=failing_commit):
            with self.assertRaises(EncryptionError):
                encrypt_packages([self.part1, self.part2], self.passphrase)

        temp_files = list(self.tmp.glob("*.enc_tmp_*")) + list(self.tmp.glob("*.cipher_tmp_*"))
        self.assertEqual(len(temp_files), 0, f"Found orphaned temp files: {temp_files}")

    def test_09_plaintext_zips_only_deleted_after_all_commit_success(self):
        """9. Plaintext ZIPs are deleted strictly after all parts commit."""
        enc_paths = encrypt_packages([self.part1, self.part2], self.passphrase)
        self.assertEqual(len(enc_paths), 2)
        self.assertFalse(self.part1.exists())
        self.assertFalse(self.part2.exists())

    def test_10_single_and_multipart_backward_compatible(self):
        """10. Single ZIP API (encrypt_package) retains identical backward-compatible behavior."""
        single_zip = self.tmp / "single.zip"
        with zipfile.ZipFile(single_zip, "w") as z:
            z.writestr("single.txt", "hello")

        enc = encrypt_package(single_zip, self.passphrase)
        self.assertEqual(enc, Path(str(single_zip) + ".enc"))
        self.assertTrue(enc.exists())
        self.assertFalse(single_zip.exists())


if __name__ == "__main__":
    unittest.main()
