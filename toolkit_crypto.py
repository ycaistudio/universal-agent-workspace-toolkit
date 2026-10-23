"""Optional package encryption.

``--encrypt`` is off unless the flag is passed. The toolkit stays on the Python
standard library and shells out to OpenSSL for the cipher. The passphrase is
read from UAWT_ENCRYPT_PASSPHRASE or from a prompt. It is never accepted as a
command-line argument.

The file written to ``*.zip.enc`` is an envelope, not raw OpenSSL output:

    magic ``UAWTENC1\\n`` | 16-byte MAC salt | 32-byte HMAC-SHA256 | ciphertext

The ciphertext is OpenSSL ``enc -aes-256-cbc -pbkdf2 -iter 200000 -salt``.
The HMAC key is PBKDF2-HMAC-SHA256 of the passphrase (200000 iterations, the
salt above). The HMAC covers the ciphertext (encrypt-then-MAC). Decrypt checks
that HMAC before it writes any output file.
"""

import hashlib
import hmac
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


OPENSSL_CIPHER = ("-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt")
PASSPHRASE_ENV = "UAWT_ENCRYPT_PASSPHRASE"
ENVELOPE_MAGIC = b"UAWTENC1\n"
MAC_SALT_LEN = 16
MAC_LEN = 32
MAC_ITERATIONS = 200000
_CHUNK = 1024 * 1024


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


def _require_passphrase(passphrase):
    if not passphrase:
        raise EncryptionError(
            f"A passphrase is required. Set {PASSPHRASE_ENV} or enter one when prompted."
        )
    return passphrase.encode("utf-8")


def _mac_key(passphrase, salt):
    return hashlib.pbkdf2_hmac("sha256", _require_passphrase(passphrase), salt, MAC_ITERATIONS, dklen=32)


def _hmac_ciphertext(path, mac_key, skip=0):
    digest = hmac.new(mac_key, digestmod=hashlib.sha256)
    with open(path, "rb") as handle:
        if skip:
            handle.seek(skip)
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.digest()


def _run_openssl(src, dst, passphrase, decrypt=False):
    _require_passphrase(passphrase)
    cmd = openssl_enc_command(src, dst, decrypt=decrypt)
    env = os.environ.copy()
    env[PASSPHRASE_ENV] = passphrase
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    except OSError as exc:
        raise EncryptionError(f"Could not run openssl: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if Path(dst).exists():
            Path(dst).unlink()
        raise EncryptionError(detail or f"openssl exited {proc.returncode}")
    try:
        os.chmod(dst, 0o600)
    except OSError:
        pass
    return Path(dst)


def _seal(ciphertext_path, enc_path, passphrase):
    salt = os.urandom(MAC_SALT_LEN)
    mac = _hmac_ciphertext(ciphertext_path, _mac_key(passphrase, salt))
    with open(enc_path, "wb") as out:
        out.write(ENVELOPE_MAGIC)
        out.write(salt)
        out.write(mac)
        with open(ciphertext_path, "rb") as src:
            while chunk := src.read(_CHUNK):
                out.write(chunk)
    try:
        os.chmod(enc_path, 0o600)
    except OSError:
        pass


def _open_envelope(enc_path, passphrase):
    """Return a temp file of ciphertext, or raise before writing decrypted output.

    The HMAC is checked first. A wrong passphrase or a modified file raises
    EncryptionError and leaves no ciphertext temp and no plaintext.
    """
    enc_path = Path(enc_path)
    header = len(ENVELOPE_MAGIC) + MAC_SALT_LEN + MAC_LEN
    try:
        with open(enc_path, "rb") as handle:
            magic = handle.read(len(ENVELOPE_MAGIC))
            salt = handle.read(MAC_SALT_LEN)
            mac = handle.read(MAC_LEN)
    except OSError as exc:
        raise EncryptionError(f"Could not read encrypted package: {exc}") from exc
    if magic != ENVELOPE_MAGIC or len(salt) != MAC_SALT_LEN or len(mac) != MAC_LEN:
        raise EncryptionError(
            "This encrypted package has no integrity header. "
            "Re-pack it with the current --encrypt. No output was written."
        )
    try:
        actual = _hmac_ciphertext(enc_path, _mac_key(passphrase, salt), skip=header)
    except EncryptionError:
        raise
    if not hmac.compare_digest(actual, mac):
        raise EncryptionError(
            "Wrong passphrase, or the encrypted file was modified. No output was written."
        )
    handle = tempfile.NamedTemporaryFile(prefix="uawt_ct_", suffix=".bin", delete=False)
    handle.close()
    temp = Path(handle.name)
    try:
        with open(enc_path, "rb") as src, open(temp, "wb") as out:
            src.seek(header)
            while chunk := src.read(_CHUNK):
                out.write(chunk)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise EncryptionError(f"Could not read ciphertext: {exc}") from exc
    return temp


def encrypt_package(zip_path, passphrase):
    """Encrypt ``zip_path`` to ``zip_path.enc`` and delete the plaintext zip.

    On failure the plaintext zip is left in place and any partial ciphertext is removed.
    """
    zip_path = Path(zip_path)
    enc_path = Path(str(zip_path) + ".enc")
    if enc_path.exists():
        enc_path.unlink()
    cipher_temp = Path(str(enc_path) + ".part")
    try:
        _run_openssl(zip_path, cipher_temp, passphrase, decrypt=False)
        _seal(cipher_temp, enc_path, passphrase)
    except EncryptionError:
        if enc_path.exists():
            enc_path.unlink()
        raise
    finally:
        if cipher_temp.exists():
            cipher_temp.unlink()
    zip_path.unlink()
    return enc_path


def decrypt_package(enc_path, passphrase, dest=None):
    """Decrypt to ``dest`` or a new temporary ``.zip``. Caller deletes temp files.

    The integrity check runs before ``dest`` is created.
    """
    enc_path = Path(enc_path)
    ciphertext = _open_envelope(enc_path, passphrase)
    if dest is None:
        handle = tempfile.NamedTemporaryFile(prefix="uawt_dec_", suffix=".zip", delete=False)
        handle.close()
        dest = Path(handle.name)
    else:
        dest = Path(dest)
    try:
        return _run_openssl(ciphertext, dest, passphrase, decrypt=True)
    finally:
        ciphertext.unlink(missing_ok=True)


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
