"""v2.3.0 hardening: part cap and split kits, name-only secret gate, venv locks,
duplicate rules, long paths, no-overwrite naming, model weights. Synthetic fixtures only."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from toolkit_crypto import openssl_path, resolve_encrypted_input, encrypt_packages  # noqa: E402
from toolkit_grok import L5, run_grok_pack, scan_grok_assets  # noqa: E402
from toolkit_pack import run_pack  # noqa: E402
from toolkit_parts import (  # noqa: E402
    PartError,
    long_path_report,
    sibling_parts,
    unique_stem,
    validate_part_mb,
)
from toolkit_preflight import emit_env_locks, find_duplicates  # noqa: E402
from toolkit_restore import cleanup_staging, unpack_and_audit  # noqa: E402
from toolkit_scanner import classify_file, scan_all_assets, secret_name_reason  # noqa: E402

FAKE_SECRET = "FAKE_SECRET_VALUE_FOR_TESTS_ONLY_0000"
SRC = "11111111-1111-4111-8111-111111111111"


def _blob(paths):
    out = b""
    for path in paths:
        with zipfile.ZipFile(path) as zipf:
            out += b"".join(zipf.read(name) for name in zipf.namelist())
    return out


def _manifest(path):
    with zipfile.ZipFile(path) as zipf:
        return json.loads(zipf.read("package_manifest.json"))


class _Home(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.ws = self.root / "ws"
        skill = self.home / ".gemini" / "config" / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("demo skill", encoding="utf-8")
        (self.home / ".gemini" / "antigravity" / "mcp").mkdir(parents=True)
        self.ws.mkdir()
        (self.ws / "AGENTS.md").write_text("directive", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()


class PartCapTests(_Home):
    def test_validate_part_mb(self):
        self.assertEqual(validate_part_mb("90"), 90_000_000)
        self.assertEqual(validate_part_mb(95), 95_000_000)
        self.assertEqual(validate_part_mb("0.5"), 500_000)
        for bad in ("95.01", "96", "200", "0", "-1", "abc", "nan"):
            with self.assertRaises(PartError, msg=bad):
                validate_part_mb(bad)

    def test_cli_rejects_part_cap_above_95(self):
        done = subprocess.run(
            [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "pack", "--max-part-mb", "96",
             "-y", "--lang", "en", "--output-dir", str(self.root / "out")],
            cwd=REPO, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn("95", done.stderr)
        self.assertFalse((self.root / "out").exists())

    def _big_kit(self):
        docs = self.ws / "docs"
        docs.mkdir()
        for index in range(6):
            (docs / f"note_{index}.bin.txt").write_bytes(os.urandom(90_000))
        (docs / "big_report.pdf").write_bytes(os.urandom(700_000))

    def test_split_roundtrip_with_chunked_file(self):
        self._big_kit()
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        cap = 300_000
        result = run_pack(assets, self.root / "out", self.home, max_part_bytes=cap)
        parts = result["zip_paths"]
        self.assertGreater(len(parts), 2)
        for index, path in enumerate(parts, start=1):
            self.assertRegex(path.name, rf"_Part_0{index}_of_0{len(parts)}\.zip$")
            self.assertLessEqual(path.stat().st_size, cap)
            with zipfile.ZipFile(path) as zipf:  # standalone, not a multi-volume archive
                self.assertIsNone(zipf.testzip())
                for name in zipf.namelist():
                    self.assertFalse(name.startswith("/") or "\\" in name or ".." in name.split("/"))
            doc = _manifest(path)
            self.assertEqual(doc["split"]["part"], index)
            self.assertEqual(doc["split"]["parts"], len(parts))
            self.assertTrue(doc["file_manifest"])
        chunked = _manifest(parts[0])["split"]["chunked_files"]
        self.assertTrue(any(rel.endswith("big_report.pdf") for rel in chunked))

        # Pointing at any one part finds the siblings, joins the chunks, verifies everything.
        audit = unpack_and_audit(parts[-1])
        try:
            self.assertIsNone(audit["error"])
            self.assertEqual(audit["corrupted_files"], [])
            self.assertEqual(len(audit["parts"]), len(parts))
            staging = Path(audit["staging_dir"])
            joined = list(staging.rglob("big_report.pdf"))
            self.assertEqual(len(joined), 1)
            self.assertEqual(joined[0].read_bytes(), (self.ws / "docs" / "big_report.pdf").read_bytes())
            self.assertFalse(list(staging.rglob("*.uawt-chunk-*")))
            self.assertFalse(any(".uawt-chunk-" in rel for rel in audit["manifest"]["file_manifest"]))
        finally:
            cleanup_staging(audit["staging_dir"])

    def test_missing_part_is_an_error(self):
        self._big_kit()
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        parts = run_pack(assets, self.root / "out", self.home, max_part_bytes=300_000)["zip_paths"]
        parts[1].unlink()
        audit = unpack_and_audit(parts[0])
        try:
            self.assertIn("incomplete", audit["error"])
        finally:
            cleanup_staging(audit["staging_dir"])

    def test_tampered_part_is_caught(self):
        self._big_kit()
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        parts = run_pack(assets, self.root / "out", self.home, max_part_bytes=300_000)["zip_paths"]
        victim = parts[-1]
        with zipfile.ZipFile(victim) as zipf:
            items = {name: zipf.read(name) for name in zipf.namelist()}
        target = next(name for name in items if name != "package_manifest.json")
        items[target] = b"tampered" + items[target]
        with zipfile.ZipFile(victim, "w") as zipf:
            for name, data in items.items():
                zipf.writestr(name, data)
        audit = unpack_and_audit(parts[0])
        try:
            self.assertTrue(audit["error"] or audit["corrupted_files"])
        finally:
            cleanup_staging(audit["staging_dir"])

    def test_small_kit_stays_one_zip(self):
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        result = run_pack(assets, self.root / "out", self.home)
        self.assertEqual(len(result["zip_paths"]), 1)
        self.assertNotIn("_Part_", result["zip_path"].name)
        self.assertNotIn("split", _manifest(result["zip_path"]))
        self.assertEqual(_manifest(result["zip_path"])["manifest_version"], "v2.3.0")

    def test_never_overwrites_existing_output(self):
        out = self.root / "pk"
        out.mkdir()
        (out / "Kit.zip").write_text("old", encoding="utf-8")
        self.assertEqual(unique_stem(out, "Kit"), "Kit_v2")
        (out / "Kit_v2.zip.enc").write_text("old", encoding="utf-8")
        self.assertEqual(unique_stem(out, "Kit"), "Kit_v3")
        (out / "Set_Part_02_of_03.zip").write_text("old", encoding="utf-8")
        self.assertEqual(unique_stem(out, "Set", 3), "Set_v2")
        self.assertEqual(unique_stem(out, "Set", 1), "Set")

    def test_long_path_advice(self):
        short = long_path_report(["a/b.md"])
        self.assertFalse(short["over_limit"])
        deep = "/".join(["very_long_folder_name_for_testing"] * 8) + "/file.md"
        report = long_path_report(["a/b.md", deep])
        self.assertTrue(report["over_limit"])
        self.assertEqual(report["max_path_chars"], len(deep))
        self.assertIn("C:\\GB\\", report["advice"])
        self.assertIn("LongPathsEnabled", report["advice"])


class SecretGateTests(_Home):
    EXCLUDED = (
        "api_secret.json", "my-token.txt", "credentials.json", "cookies.sqlite", "service_key.json",
        "key.json", "gateway.json", "mcp_config.json", ".env", "server.pem", "server.key",
        "Secrets.yaml", "access_TOKEN.cfg",
    )
    KEPT = (
        "tokenizer.json", "tokenizer_config.json", "package-lock.json", "keybindings.json",
        "secretariat_notes.md", "token_budget.md", "cookie_recipe.md", "credential_check.py",
        "keyboard.json", "monkey.json", "README.md",
    )

    def test_name_rules(self):
        for name in self.EXCLUDED:
            self.assertIsNotNone(secret_name_reason(Path(name)), name)
        for name in self.KEPT:
            self.assertIsNone(secret_name_reason(Path(name)), name)

    def test_scan_excludes_by_name_without_reading(self):
        notes = self.ws / "notes"
        notes.mkdir()
        for name in self.EXCLUDED:
            (notes / name).write_text(FAKE_SECRET, encoding="utf-8")
        for name in ("tokenizer.json", "keybindings.json"):
            (notes / name).write_text('{"ok": true}', encoding="utf-8")
        (notes / "Secretariat.md").write_text("meeting minutes", encoding="utf-8")
        creds = self.ws / "credentials"
        creds.mkdir()
        (creds / "plain.txt").write_text(FAKE_SECRET, encoding="utf-8")

        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        excluded = {str(path) for path, _ in assets["excluded"]}
        for name in self.EXCLUDED:
            self.assertIn(str(notes / name), excluded, name)
        self.assertTrue(any(path.endswith("credentials") for path in excluded))
        l4 = {path.name for path in assets["Level_4_Workspace_Docs"]}
        self.assertTrue({"tokenizer.json", "keybindings.json", "Secretariat.md"} <= l4)

        result = run_pack(assets, self.root / "out", self.home)
        self.assertNotIn(FAKE_SECRET.encode(), _blob(result["zip_paths"]))

    def test_grok_box_credentials_and_secret_names(self):
        data = self.root / "agent-data"
        ws = self.root / "box-ws"
        agent = data / "agents" / SRC
        agent.mkdir(parents=True)
        (agent / "profile.json").write_text(json.dumps({"name": "Demo"}), encoding="utf-8")
        (data / "credentials").mkdir()
        (data / "credentials" / "anything.md").write_text(FAKE_SECRET, encoding="utf-8")
        ws.mkdir()
        (ws / "deploy.pem").write_text(FAKE_SECRET, encoding="utf-8")
        (ws / "session_cookie.txt").write_text(FAKE_SECRET, encoding="utf-8")
        (ws / "Secretariat.md").write_text("doc", encoding="utf-8")
        paths = {"agent_data": data, "workspace": ws, "memory_drop": ws / "none",
                 "cursor_stores": self.root / "none", "search_index": data / "search-index.db"}
        out = self.root / "gout"
        assets = scan_grok_assets(paths, exclude_roots=[out])
        result = run_grok_pack(assets, out, Path("/home/alice"), env_lock=False)
        blob = _blob(result["zip_paths"])
        self.assertNotIn(FAKE_SECRET.encode(), blob)
        self.assertIn(b"doc", blob)
        mode = stat.S_IMODE(result["zip_path"].stat().st_mode)
        self.assertEqual(mode & 0o077, 0)

    def test_include_secrets_still_honoured_for_content_rules(self):
        # classify_file keeps its old contract: returns a tuple and never includes file contents.
        path = self.ws / "api_token.json"
        path.write_text(FAKE_SECRET, encoding="utf-8")
        verdict, reason = classify_file(path)
        self.assertEqual(verdict, "exclude")
        self.assertNotIn(FAKE_SECRET, reason)


class VenvAndModelTests(_Home):
    def _fake_venv(self, where):
        venv = where / ".venv"
        bindir = venv / "bin"
        bindir.mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        site = venv / "lib" / "python3" / "site-packages" / "fakepkg"
        site.mkdir(parents=True)
        (site / "__init__.py").write_text("SITE_PACKAGES_SENTINEL = 1\n", encoding="utf-8")
        python = bindir / "python"
        python.write_text("#!/bin/sh\necho 'fakepkg==1.0.0'\n", encoding="utf-8")
        python.chmod(0o755)
        return venv

    @unittest.skipIf(os.name == "nt", "shell-script fake interpreter")
    def test_venv_excluded_and_frozen_offline(self):
        self._fake_venv(self.ws / "tool")
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        self.assertTrue(assets["venvs"])
        result = run_pack(assets, self.root / "out", self.home)
        blob = _blob(result["zip_paths"])
        self.assertNotIn(b"SITE_PACKAGES_SENTINEL", blob)
        with zipfile.ZipFile(result["zip_path"]) as zipf:
            locks = [n for n in zipf.namelist() if "python-envs/requirements-" in n]
            self.assertEqual(len(locks), 1, zipf.namelist())
            self.assertIn(b"fakepkg==1.0.0", zipf.read(locks[0]))
            self.assertTrue(any(n.endswith("python-envs/pip-user-packages.txt") for n in zipf.namelist()))
        doc = _manifest(result["zip_path"])
        self.assertEqual(doc["env_locks"]["venvs"][0]["status"], "ok")

    def test_skip_env_lock(self):
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        result = run_pack(assets, self.root / "out", self.home, env_lock=False)
        with zipfile.ZipFile(result["zip_path"]) as zipf:
            self.assertFalse(any("python-envs" in n for n in zipf.namelist()))

    def test_broken_venv_reports_error_not_crash(self):
        venv = self.root / "broken" / "venv"
        venv.mkdir(parents=True)
        report = emit_env_locks([venv], self.root / "locks", include_user=False)
        self.assertNotEqual(report["venvs"][0]["status"], "ok")

    def test_model_weights_need_include_bulky(self):
        models = self.ws / "models"
        models.mkdir()
        (models / "tiny.onnx").write_bytes(b"x" * 6_000_000)
        (models / "small.bin").write_bytes(b"x" * 1000)
        default = scan_all_assets(self.home, self.ws, include_secrets=False)
        l4 = {p.name for p in default["Level_4_Workspace_Docs"]}
        self.assertNotIn("tiny.onnx", l4)
        self.assertIn("small.bin", l4)
        self.assertTrue(any(Path(p).name == "tiny.onnx" for p, _ in default["Level_5_Heavy_References"]))
        bulky = scan_all_assets(self.home, self.ws, include_secrets=False, include_bulky=True)
        self.assertIn("tiny.onnx", {p.name for p in bulky["Level_4_Workspace_Docs"]})

    def test_grok_model_weights_go_to_level5(self):
        data = self.root / "agent-data"
        ws = self.root / "box-ws"
        (data / "agents" / SRC).mkdir(parents=True)
        (data / "agents" / SRC / "profile.json").write_text("{}", encoding="utf-8")
        ws.mkdir()
        (ws / "model.safetensors").write_bytes(b"x" * 6_000_000)
        paths = {"agent_data": data, "workspace": ws, "memory_drop": ws / "none",
                 "cursor_stores": self.root / "none", "search_index": data / "search-index.db"}
        def level_of(assets):
            return next(f["level"] for f in assets["files"] if f["src"].name == "model.safetensors")

        assets = scan_grok_assets(paths)
        self.assertEqual(level_of(assets), L5)
        self.assertTrue(any(Path(fp).name == "model.safetensors" for fp, _ in assets["flagged"]))
        bulky = scan_grok_assets(paths, include_bulky=True)
        self.assertFalse(any(Path(fp).name == "model.safetensors" for fp, _ in bulky["flagged"]))
        self.assertNotEqual(level_of(bulky), L5)


class DuplicateTests(_Home):
    def test_duplicate_rule_trees_are_flagged(self):
        a = self.ws / "skills_a" / "writer"
        b = self.ws / "backup" / "skills" / "writer"
        c = self.ws / "other" / "writer"
        for folder, body in ((a, "same"), (b, "same"), (c, "different")):
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(body, encoding="utf-8")
        groups = find_duplicates([a / "SKILL.md", b / "SKILL.md", c / "SKILL.md"])
        kinds = {g["kind"] for g in groups}
        self.assertEqual(kinds, {"identical", "diverged"})
        identical = next(g for g in groups if g["kind"] == "identical")
        self.assertEqual(len(identical["locations"]), 2)
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        self.assertTrue(assets["duplicates"])
        result = run_pack(assets, self.root / "out", self.home)
        self.assertTrue(_manifest(result["zip_path"])["duplicates"])


class CliTests(_Home):
    def _env(self):
        env = os.environ.copy()
        env["UAWT_PROFILE"] = "antigravity"
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        return env

    def test_cli_split_pack_inspect_restore(self):
        docs = self.ws / "docs"
        docs.mkdir()
        (docs / "big.dat.txt").write_bytes(os.urandom(800_000))
        out = self.root / "out"
        packed = subprocess.run(
            [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "pack", "--profile", "antigravity",
             "--workspace-dir", str(self.ws), "--max-part-mb", "0.4", "-y", "--lang", "en",
             "--output-dir", str(out)],
            cwd=REPO, env=self._env(), capture_output=True, text=True, timeout=120)
        self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)
        parts = sorted(out.glob("packages/*_Part_*.zip"))
        self.assertGreaterEqual(len(parts), 2, packed.stdout)
        self.assertIn("standalone parts", packed.stdout)
        inspected = subprocess.run(
            [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "inspect",
             "--input-dir", str(parts[0]), "--lang", "en"],
            cwd=REPO, env=self._env(), capture_output=True, text=True, timeout=120)
        self.assertEqual(inspected.returncode, 0, inspected.stdout + inspected.stderr)
        self.assertIn("[Parts]", inspected.stdout)

        # A second pack never overwrites the first set.
        again = subprocess.run(
            [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "pack", "--profile", "antigravity",
             "--workspace-dir", str(self.ws), "--max-part-mb", "0.4", "-y", "--lang", "en",
             "--output-dir", str(out)],
            cwd=REPO, env=self._env(), capture_output=True, text=True, timeout=120)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        for part in parts:
            self.assertTrue(part.exists())

        parts[-1].unlink()
        broken = subprocess.run(
            [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "inspect",
             "--input-dir", str(parts[0]), "--lang", "en"],
            cwd=REPO, env=self._env(), capture_output=True, text=True, timeout=120)
        self.assertEqual(broken.returncode, 2, broken.stdout + broken.stderr)


@unittest.skipUnless(openssl_path(), "openssl not installed")
class EncryptedPartTests(_Home):
    def test_encrypt_every_part_and_restore(self):
        docs = self.ws / "docs"
        docs.mkdir()
        (docs / "big.dat.txt").write_bytes(os.urandom(700_000))
        assets = scan_all_assets(self.home, self.ws, include_secrets=False)
        parts = run_pack(assets, self.root / "out", self.home, max_part_bytes=300_000)["zip_paths"]
        encrypted = encrypt_packages(parts, "correct horse battery staple")
        self.assertEqual(len(encrypted), len(parts))
        for path in parts:
            self.assertFalse(path.exists())
        with self.assertRaises(Exception):
            encrypt_packages([encrypted[0].with_suffix("")], "x")  # .enc already exists -> refuse
        folder, temps = resolve_encrypted_input(encrypted[0], "correct horse battery staple")
        try:
            audit = unpack_and_audit(folder)
            try:
                self.assertIsNone(audit["error"])
                self.assertEqual(audit["corrupted_files"], [])
                self.assertEqual(len(audit["parts"]), len(parts))
            finally:
                cleanup_staging(audit["staging_dir"])
        finally:
            for temp in temps:
                shutil.rmtree(temp, ignore_errors=True) if Path(temp).is_dir() else Path(temp).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
