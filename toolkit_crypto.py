"""Optional package encryption.

The toolkit stays on the Python standard library. ``--encrypt`` shells out to
OpenSSL when that binary is on PATH. It is not required for pack, restore, or
inspect. The passphrase is read from the environment variable
UAWT_ENCRYPT_PASSPHRASE or from a prompt. It is never accepted as a command-line
argument.

Manual equivalent (same flags the toolkit uses):

    openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \\
        -in PACKAGE.zip -out PACKAGE.zip.enc -pass env:UAWT_ENCRYPT_PASSPHRASE
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -salt \\
        -in PACKAGE.zip.enc -out PACKAGE.zip -pass env:UAWT_ENCRYPT_PASSPHRASE
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


OPENSSL_CIPHER = ("-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt")
PASSPHRASE_ENV = "UAWT_ENCRYPT_PASSPHRASE"


class EncryptionError(Exception):
    """Raised when encryption was requested but cannot be completed safely."""


def openssl_path():
    return shutil.which("openssl")


def openssl_enc_command(src, dst, decrypt=False):
    """Build the OpenSSL argv. The passphrase stays in the child environment."""
    binary = openssl_path()
    if not binary:
        raise EncryptionError(
            "openssl was not found on PATH. --encrypt needs the OpenSSL enc "
            "command (AES-256-CBC, PBKDF2, 200000 iterations). "
            "Install OpenSSL or rerun without --encrypt."
        )
    cmd = [binary, "enc", *OPENSSL_CIPHER, "-in", str(src), "-out", str(dst),
           "-pass", f"env:{PASSPHRASE_ENV}"]
    if decrypt:
        cmd.insert(2, "-d")
    return cmd


def _run_openssl(src, dst, passphrase, decrypt=False):
    if not passphrase:
        raise EncryptionError(
            f"A passphrase is required. Set {PASSPHRASE_ENV} or enter one when prompted."
        )
    cmd = openssl_enc_command(src, dst, decrypt=decrypt)
    env = os.environ.copy()
    env[PASSPHRASE_ENV] = passphrase
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    except OSError as exc:
        raise EncryptionError(f"Could not run openssl: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if dst.exists():
            dst.unlink()
        raise EncryptionError(detail or f"openssl exited {proc.returncode}")
    try:
        os.chmod(dst, 0o600)
    except OSError:
        pass
    return dst


def encrypt_package(zip_path, passphrase):
    """Encrypt ``zip_path`` to ``zip_path.enc`` and delete the plaintext zip.

    On failure the plaintext zip is left in place and any partial ciphertext is removed.
    """
    zip_path = Path(zip_path)
    enc_path = Path(str(zip_path) + ".enc")
    if enc_path.exists():
        enc_path.unlink()
    try:
        _run_openssl(zip_path, enc_path, passphrase, decrypt=False)
    except EncryptionError:
        if enc_path.exists():
            enc_path.unlink()
        raise
    zip_path.unlink()
    return enc_path


def decrypt_package(enc_path, passphrase, dest=None):
    """Decrypt to ``dest`` or a new temporary ``.zip``. Caller deletes temp files."""
    enc_path = Path(enc_path)
    if dest is None:
        handle = tempfile.NamedTemporaryFile(prefix="uawt_dec_", suffix=".zip", delete=False)
        handle.close()
        dest = Path(handle.name)
    else:
        dest = Path(dest)
    return _run_openssl(enc_path, dest, passphrase, decrypt=True)


def _level_archives(input_path):
    """Return Level_*.zip and Level_*.zip.enc candidates for a file or directory."""
    path = Path(input_path)
    if path.is_file():
        return [path]
    found = []
    for base in (path / "packages", path):
        if not base.is_dir():
            continue
        found.extend(base.glob("Level_*.zip"))
        found.extend(base.glob("Level_*.zip.enc"))
    unique = {}
    for item in found:
        unique[str(item.resolve())] = item
    return list(unique.values())


def encrypted_candidate(input_path):
    """The encrypted archive that would be restored, or None.

    A newer plaintext ``Level_*.zip`` wins, so a directory that only has zip
    files (the Antigravity case) never asks for a passphrase.
    """
    path = Path(input_path)
    if path.is_file():
        return path if path.name.endswith(".zip.enc") else None
    archives = _level_archives(path)
    encs = [item for item in archives if item.name.endswith(".zip.enc")]
    zips = [item for item in archives if item.suffix.lower() == ".zip"]
    if not encs:
        return None
    newest_enc = max(encs, key=lambda item: item.stat().st_mtime)
    if zips and max(item.stat().st_mtime for item in zips) >= newest_enc.stat().st_mtime:
        return None
    return newest_enc


def resolve_encrypted_input(input_path, passphrase):
    """Return ``(path_for_audit, temp_files)``.

    When no encrypted archive is selected, ``path_for_audit`` is the original
    input so the Antigravity package picker is unchanged.
    """
    chosen = encrypted_candidate(input_path)
    if chosen is None:
        return Path(input_path), []
    decrypted = decrypt_package(chosen, passphrase)
    return decrypted, [decrypted]
