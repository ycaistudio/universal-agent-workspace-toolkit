"""Synthetic Grok Bot box: pack, secret gate, conservative restore, encryption."""

import json
import os
import sqlite3
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from toolkit_crypto import (  # noqa: E402
    OPENSSL_CIPHER,
    encrypt_package,
    encrypted_candidate,
    openssl_enc_command,
    openssl_path,
    resolve_encrypted_input,
)
from toolkit_grok import (  # noqa: E402
    GrokError,
    L3,
    L5,
    L6,
    L7,
    L8,
    build_restore_plan,
    create_grok_snapshot,
    detect_profile,
    execute_grok_restore,
    parse_uuid_map,
    run_grok_pack,
    scan_grok_assets,
    valid_agent_id,
)
from toolkit_restore import cleanup_staging, unpack_and_audit  # noqa: E402
from toolkit_scanner import REDACTED  # noqa: E402

SRC = "11111111-1111-4111-8111-111111111111"
DST = "22222222-2222-4222-8222-222222222222"
FACT = "UNIQUE_FACT_SENTINEL_grok"
BODY = "UNIQUE_BODY_SENTINEL_grok"
BOX_SECRET = "UNIQUE_BOX_SECRET_grok"
TOP_SECRET = "UNIQUE_TOP_SECRET_grok"
NESTED_OK = "UNIQUE_NESTED_OK_grok"
GATEWAY = "UNIQUE_GATEWAY_grok"
MANAGED = "UNIQUE_MANAGED_SKILL_grok"
PLUGIN = "UNIQUE_PLUGIN_SKILL_grok"
SUBAGENT = "UNIQUE_SUBAGENT_grok"
VIDEO = "UNIQUE_VIDEO_grok"
TOKEN = "sk-abcdefghijklmnopqrstuvwxyz1234"


def _zip_blob(path):
    blob = bytearray()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            blob.extend(archive.read(info))
    return bytes(blob)


def _manifest(path):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("package_manifest.json"))


class DetectTests(unittest.TestCase):
    def test_auto_requires_agent_data_directory(self):
        # --profile auto does not follow UAWT_PROFILE, and a missing directory stays Antigravity.
        self.assertEqual(detect_profile("auto", {"UAWT_PROFILE": "grok"}), "antigravity")
        self.assertEqual(detect_profile(None, {"UAWT_PROFILE": "grok"}), "grok")
        self.assertEqual(detect_profile("antigravity", {"GROK_AGENT_DATA": "/no/such/agent-data"}), "antigravity")
        self.assertEqual(detect_profile(None, {}), "antigravity")

    def test_auto_selects_grok_when_agent_data_exists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "agent-data"
            data.mkdir()
            env = {"GROK_AGENT_DATA": str(data), "GROK_WORKSPACE": str(Path(tmp) / "ws")}
            self.assertEqual(detect_profile("auto", env), "grok")
            self.assertEqual(detect_profile("antigravity", env), "antigravity")


class AgentIdTests(unittest.TestCase):
    def test_accepts_hyphenated_uuid_and_32_hex(self):
        self.assertTrue(valid_agent_id("11111111-1111-4111-8111-111111111111"))
        self.assertTrue(valid_agent_id("11111111111141118111111111111111"))
        self.assertTrue(valid_agent_id("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"))

    def test_rejects_folder_names_and_decorated_uuid_text(self):
        self.assertFalse(valid_agent_id("lobby"))
        self.assertFalse(valid_agent_id("desk"))
        self.assertFalse(valid_agent_id(""))
        self.assertFalse(valid_agent_id(None))
        self.assertFalse(valid_agent_id("{11111111-1111-4111-8111-111111111111}"))
        self.assertFalse(valid_agent_id("urn:uuid:11111111-1111-4111-8111-111111111111"))
        self.assertFalse(valid_agent_id("11111111-1111-4111-8111-11111111111"))
        self.assertFalse(valid_agent_id("11111111-11111111-1111-111111111111"))


class GrokBoxTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src_ws = self.root / "boxsrc" / "workspace"
        self.src_data = self.root / "boxsrc" / "agent-data"
        self.drop = self.src_ws / "exports" / "memory-drop"
        self.stores = self.root / "stores"
        self.out = self.root / "out"
        self._build()

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self):
        agent = self.src_data / "agents" / SRC
        (agent / "automations").mkdir(parents=True)
        (agent / "notes").mkdir()
        (agent / "private").mkdir()
        (agent / "profile.json").write_text(
            json.dumps({"name": "Field Bot", "description": f"owns {SRC}"}), encoding="utf-8")
        (agent / "settings.json").write_text(
            json.dumps({"token": TOKEN, "theme": "calm"}), encoding="utf-8")
        (agent / "avatar.png").write_bytes(b"\x89PNG-fake")
        (agent / "automations" / "daily.json").write_text(
            json.dumps({"name": "daily", "agent": SRC}), encoding="utf-8")
        (agent / "notes" / "memo.md").write_text("FIELD_MEMO_SENTINEL_grok", encoding="utf-8")
        (agent / "notes" / "custom-secrets.json").write_text(NESTED_OK, encoding="utf-8")
        (agent / "notes" / "gateway.json").write_text(GATEWAY, encoding="utf-8")
        (agent / "private" / "note.txt").write_text("PRIVATE_NOTE_SENTINEL_grok", encoding="utf-8")

        for name, text in {
            "box-secrets.json": BOX_SECRET,
            "host-secrets.json": "host",
            "chrome-cookie-seed.json": "cookie",
            "gateway.json": GATEWAY,
            "teach-queue-key.json": "teach",
            "custom-secrets.json": TOP_SECRET,
        }.items():
            (self.src_data / name).write_text(text, encoding="utf-8")

        skill = self.src_data / "workflows" / "real-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"skill {SRC}\n{self.src_ws}/hello.md\n{self.src_data}/agents/{SRC}/profile.json\n/home/alice/notes\n",
            encoding="utf-8")
        managed = self.src_data / "managed-skills" / "host"
        managed.mkdir(parents=True)
        (managed / "SKILL.md").write_text(MANAGED, encoding="utf-8")
        plugin = self.src_data / "plugin-skills" / "plug"
        plugin.mkdir(parents=True)
        (plugin / "SKILL.md").write_text(PLUGIN, encoding="utf-8")
        nested = self.src_data / "workflows" / "plugin-skills" / "evil"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text(PLUGIN, encoding="utf-8")

        (self.src_data / "agents" / "lobby").mkdir(parents=True)
        (self.src_data / "agents" / "lobby" / "profile.json").write_text(
            '{"label":"not-a-bot"}', encoding="utf-8")
        (self.src_data / "agents" / "catalog.json").write_text(
            '{"listed": false}', encoding="utf-8")

        self.src_ws.mkdir(parents=True)
        (self.src_ws / "hello.md").write_text(
            f"bot {SRC}\npath {self.src_ws}/hello.md\n/home/alice/notes\n", encoding="utf-8")
        (self.src_ws / "AGENTS.md").write_text(f"directive {SRC}\n", encoding="utf-8")
        (self.src_ws / "clip.mp4").write_text(VIDEO, encoding="utf-8")

        drop_agent = self.drop / "agents" / SRC
        drop_agent.mkdir(parents=True)
        (drop_agent / "memory-profile.jsonl").write_text(
            json.dumps({"fact": FACT, "written": "2026-03-04", "kind": "durable"}) + "\n",
            encoding="utf-8")
        (self.drop / "shared-user").mkdir()
        (self.drop / "shared-user" / "memory-user.jsonl").write_text(
            json.dumps({"fact": "ACCOUNT_MEMORY_SENTINEL_grok", "written": "2026-03-04", "kind": "account"}) + "\n",
            encoding="utf-8")

        transcript = self.src_data / "agent-transcripts" / SRC
        transcript.mkdir(parents=True)
        (transcript / f"{SRC}.jsonl").write_text('{"role":"user","message":{"content":[{"type":"text","text":"hi"}]}}\n',
                                                 encoding="utf-8")
        sand = self.src_data / "agent-transcripts" / "sand-subagent-1"
        sand.mkdir()
        (sand / "log.jsonl").write_text(SUBAGENT, encoding="utf-8")

        conn = sqlite3.connect(self.src_data / "search-index.db")
        # The packer groups on messages.agent_id, which is the platform column.
        # note_text is only here so the test can see that the snapshot kept the row payload.
        conn.execute("create table messages (agent_id text, note_text text)")
        conn.execute(
            "insert into messages (agent_id, note_text) values (?, ?)",
            (SRC, BODY))
        conn.execute(
            "insert into messages (agent_id, note_text) values (?, ?)",
            ("lobby", "PLATFORM_ROW_SENTINEL_grok"))
        conn.commit()
        conn.close()

        page = self.stores / "user" / "canvases"
        page.mkdir(parents=True)
        (page / "page.txt").write_text("UNIQUE_CANVAS_grok", encoding="utf-8")
        (self.stores / "self").symlink_to("user")

    def _paths(self):
        return {
            "agent_data": self.src_data,
            "workspace": self.src_ws,
            "memory_drop": self.drop,
            "cursor_stores": self.stores,
            "search_index": self.src_data / "search-index.db",
        }

    def _pack(self, **kwargs):
        assets = scan_grok_assets(self._paths(), exclude_roots=[self.out], **kwargs)
        return assets, run_grok_pack(assets, self.out, Path("/home/alice"))

    def test_pack_excludes_secrets_and_snapshots_conversations(self):
        assets, result = self._pack()
        blob = _zip_blob(result["zip_path"])
        manifest = _manifest(result["zip_path"])
        self.assertEqual(manifest["profile"], "grok")
        for secret in (BOX_SECRET, TOP_SECRET, GATEWAY, MANAGED, PLUGIN, SUBAGENT, VIDEO, TOKEN):
            self.assertNotIn(secret.encode(), blob)
        self.assertIn(NESTED_OK.encode(), blob)
        self.assertIn(FACT.encode(), blob)
        self.assertNotIn(FACT, json.dumps(manifest["memory_drop"]))
        self.assertEqual(manifest["conversations"]["consistent_snapshot"], True)
        self.assertEqual(manifest["conversations"]["platform_message_rows"], 1)
        ids = [agent["id"] for agent in manifest["conversations"]["agents"]]
        self.assertIn(SRC, ids)
        self.assertNotIn("lobby", ids)
        self.assertEqual(next(agent["messages"] for agent in manifest["conversations"]["agents"] if agent["id"] == SRC), 1)
        with zipfile.ZipFile(result["zip_path"]) as archive:
            stats = archive.read("Level_7_Conversations/conversation-stats.json").decode()
            self.assertNotIn(BODY, stats)
            snapshot = self.root / "snap.db"
            snapshot.write_bytes(archive.read("Level_7_Conversations/search-index-snapshot.db"))
        with sqlite3.connect(snapshot) as conn:
            rows = conn.execute("select agent_id, note_text from messages").fetchall()
            self.assertCountEqual(rows, [(SRC, BODY), ("lobby", "PLATFORM_ROW_SENTINEL_grok")])
        names = [item["arc"] for item in assets["files"] if item["level"] == L5]
        self.assertTrue(any(name.endswith("clip.mp4") for name in names))
        self.assertTrue(any(item["level"] == L6 and item["arc"].endswith("memory-profile.jsonl") for item in assets["files"]))
        self.assertTrue(any(item["level"] == L3 and item["arc"] == "real-skill/SKILL.md" for item in assets["files"]))
        self.assertFalse(any(item["level"] == L8 for item in assets["files"]))
        self.assertEqual(manifest["experimental"]["cursor_stores"]["verified"], False)
        self.assertIn("user", [entry["name"] for entry in manifest["experimental"]["cursor_stores"]["entries"]])
        packed_settings = zipfile.ZipFile(result["zip_path"]).read(
            f"Level_2_System_Settings/agents/{SRC}/settings.json").decode()
        self.assertIn(REDACTED, packed_settings)
        self.assertIn("calm", packed_settings)
        self.assertNotIn("managed-skills", "\n".join(zipfile.ZipFile(result["zip_path"]).namelist()))
        self.assertNotIn("plugin-skills", "\n".join(zipfile.ZipFile(result["zip_path"]).namelist()))

    def test_restore_keeps_live_platform_files_and_remaps(self):
        _, result = self._pack()
        dest_ws = self.root / "boxdst" / "workspace"
        dest_data = self.root / "boxdst" / "agent-data"
        bot = dest_data / "agents" / DST
        (bot / "automations").mkdir(parents=True)
        (bot / "profile.json").write_text('{"name":"KEEP"}', encoding="utf-8")
        (dest_data / "search-index.db").write_text("SENTINEL_INDEX", encoding="utf-8")
        (dest_data / "agent-transcripts" / DST).mkdir(parents=True)
        (dest_data / "agent-transcripts" / DST / "keep.jsonl").write_text("KEEP_TRANSCRIPT", encoding="utf-8")
        dest_ws.mkdir(parents=True)
        (dest_ws / "hello.md").write_text("OLD_HELLO", encoding="utf-8")
        (dest_ws / "AGENTS.md").write_text("LOCAL_DIRECTIVE", encoding="utf-8")
        (dest_data / "workflows" / "real-skill").mkdir(parents=True)
        (dest_data / "workflows" / "real-skill" / "SKILL.md").write_text("OLD_SKILL", encoding="utf-8")
        target_stores = self.root / "boxdst" / "stores"
        target_stores.mkdir()
        (target_stores / "page.txt").write_text("STORE_KEEP", encoding="utf-8")

        audit = unpack_and_audit(result["zip_path"])
        self.addCleanup(lambda: cleanup_staging(audit["staging_dir"]))
        self.assertEqual(audit["corrupted_files"], [])
        uuid_map = parse_uuid_map([f"{SRC}={DST}"])
        dest = {
            "agent_data": dest_data,
            "workspace": dest_ws,
            "memory_drop": dest_ws / "exports" / "memory-drop",
            "cursor_stores": target_stores,
            "search_index": dest_data / "search-index.db",
        }
        plan = build_restore_plan(audit["staging_dir"], audit["manifest"], dest, "existing", uuid_map)
        snap = create_grok_snapshot(dest_ws, dest_data, plan["actions"])
        restored = execute_grok_restore(plan, audit["manifest"], Path("/home/bob"), dest, uuid_map, lang="en")

        self.assertEqual((bot / "profile.json").read_text(encoding="utf-8"), '{"name":"KEEP"}')
        incoming = (bot / "profile.json.incoming").read_text(encoding="utf-8")
        self.assertIn(DST, incoming)
        self.assertNotIn(SRC, incoming)
        self.assertTrue((bot / "settings.json.incoming").is_file())
        self.assertFalse((bot / "settings.json").exists())
        self.assertTrue((bot / "automations" / "daily.json.incoming").is_file())
        self.assertFalse((bot / "automations" / "daily.json").exists())
        self.assertTrue((bot / "memory-profile.jsonl.incoming").is_file())
        self.assertIn(FACT, (bot / "memory-profile.jsonl.incoming").read_text(encoding="utf-8"))
        self.assertFalse((bot / "notes").exists())
        self.assertFalse((bot / "private").exists())
        self.assertEqual((dest_data / "search-index.db").read_text(encoding="utf-8"), "SENTINEL_INDEX")
        self.assertEqual((dest_data / "agent-transcripts" / DST / "keep.jsonl").read_text(encoding="utf-8"), "KEEP_TRANSCRIPT")
        self.assertEqual((target_stores / "page.txt").read_text(encoding="utf-8"), "STORE_KEEP")

        hello = (dest_ws / "hello.md").read_text(encoding="utf-8")
        self.assertIn(DST, hello)
        self.assertIn(f"{dest_ws}/hello.md", hello)
        self.assertIn("/home/bob/notes", hello)
        self.assertNotIn(SRC, hello)
        self.assertEqual((dest_ws / "AGENTS.md").read_text(encoding="utf-8"), "LOCAL_DIRECTIVE")
        self.assertIn(DST, (dest_ws / "AGENTS.md.incoming").read_text(encoding="utf-8"))
        skill = (dest_data / "workflows" / "real-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(DST, skill)
        self.assertIn(str(dest_data), skill)
        self.assertIn("/home/bob/notes", skill)
        self.assertNotIn(SRC, skill)
        self.assertIn("OLD_HELLO", (snap / "workspace" / "hello.md").read_text(encoding="utf-8"))
        self.assertIn("OLD_SKILL", (snap / "agent-data" / "workflows" / "real-skill" / "SKILL.md").read_text(encoding="utf-8"))

        checklist = restored["checklist"].read_text(encoding="utf-8")
        self.assertIn("search-index", checklist)
        self.assertIn("experimental", checklist.lower())
        self.assertIn(DST, checklist)
        kit_snapshot = restored["incoming_dir"] / L7 / "search-index-snapshot.db"
        self.assertTrue(kit_snapshot.is_file())
        self.assertNotEqual(kit_snapshot.read_bytes(), b"SENTINEL_INDEX")

    def test_restore_does_not_create_a_missing_agent_directory(self):
        _, result = self._pack()
        dest_ws = self.root / "fresh" / "workspace"
        dest_data = self.root / "fresh" / "agent-data"
        dest_data.mkdir(parents=True)
        (dest_data / "search-index.db").write_bytes(b"SENTINEL")
        audit = unpack_and_audit(result["zip_path"])
        self.addCleanup(lambda: cleanup_staging(audit["staging_dir"]))
        dest = {
            "agent_data": dest_data,
            "workspace": dest_ws,
            "memory_drop": dest_ws / "exports" / "memory-drop",
            "cursor_stores": self.stores,
            "search_index": dest_data / "search-index.db",
        }
        plan = build_restore_plan(audit["staging_dir"], audit["manifest"], dest, "existing", {SRC: DST})
        execute_grok_restore(plan, audit["manifest"], Path("/home/bob"), dest, {SRC: DST}, lang="zh-tw")
        self.assertFalse((dest_data / "agents" / DST).exists())
        self.assertFalse((dest_data / "agents" / SRC).exists())
        self.assertTrue((dest_ws / "hello.md").is_file())
        self.assertTrue((dest_data / "workflows" / "real-skill" / "SKILL.md").is_file())
        self.assertEqual((dest_data / "search-index.db").read_bytes(), b"SENTINEL")
        checklist = list(dest_ws.glob(".grok-restore-incoming/*/MANUAL_REBUILD.md"))
        self.assertEqual(len(checklist), 1)
        self.assertIn("不要用", checklist[0].read_text(encoding="utf-8"))

    def test_optional_flags_and_bad_uuid_map(self):
        assets = scan_grok_assets(self._paths(), include_cursor_stores=True, include_subagents=True)
        self.assertTrue(any(item["level"] == L8 for item in assets["files"]))
        self.assertTrue(any("sand-subagent-1" in item["arc"] for item in assets["files"]))
        with self.assertRaises(GrokError):
            parse_uuid_map(["not-a-uuid=also-bad"])
        packed = run_grok_pack(
            scan_grok_assets(self._paths(), include_secrets=True), self.root / "secrets-out", Path("/home/alice"))
        blob = _zip_blob(packed["zip_path"])
        self.assertIn(BOX_SECRET.encode(), blob)
        self.assertIn(TOKEN.encode(), blob)

    def test_encrypt_roundtrip_uses_openssl(self):
        if not openssl_path():
            self.skipTest("openssl is not installed")
        self.assertIn("-pbkdf2", OPENSSL_CIPHER)
        self.assertIn("200000", OPENSSL_CIPHER)
        _, result = self._pack()
        zip_path = result["zip_path"]
        original = zip_path.read_bytes()
        enc = encrypt_package(zip_path, "test-passphrase")
        self.assertFalse(zip_path.exists())
        self.assertTrue(str(enc).endswith(".zip.enc"))
        command = openssl_enc_command(enc, zip_path, decrypt=True)
        self.assertIn("-d", command)
        self.assertIn("-pbkdf2", command)
        decrypted, temps = resolve_encrypted_input(enc, "test-passphrase")
        try:
            self.assertEqual(Path(decrypted).read_bytes()[:2], b"PK")
            self.assertEqual(_manifest(decrypted)["profile"], "grok")
        finally:
            for temp in temps:
                Path(temp).unlink(missing_ok=True)
        self.assertEqual(original[:2], b"PK")
        with self.assertRaises(Exception):
            resolve_encrypted_input(enc, "wrong-passphrase")
        # A newer plaintext zip is preferred over an older encrypted archive.
        plain = enc.with_name("Level_1_to_7_Grok_Bot_newer.zip")
        plain.write_bytes(original)
        os.utime(plain, None)
        self.assertIsNone(encrypted_candidate(plain.parent))


class CliTests(unittest.TestCase):
    def test_cli_grok_profile_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_data = root / "src-data"
            src_ws = root / "src-ws"
            (src_data / "agents" / SRC).mkdir(parents=True)
            (src_data / "agents" / SRC / "profile.json").write_text(
                json.dumps({"name": "Cli Bot", "description": SRC}), encoding="utf-8")
            (src_data / "workflows" / "demo").mkdir(parents=True)
            (src_data / "workflows" / "demo" / "SKILL.md").write_text(f"use {SRC}\n", encoding="utf-8")
            src_ws.mkdir()
            (src_ws / "note.md").write_text(f"see {SRC} at {src_ws}\n", encoding="utf-8")
            out = root / "packages-out"
            env = os.environ.copy()
            env.update({
                "GROK_AGENT_DATA": str(src_data),
                "GROK_WORKSPACE": str(src_ws),
                "GROK_MEMORY_DROP": str(root / "no-memory"),
                "GROK_CURSOR_STORES": str(root / "no-stores"),
                "UAWT_PROFILE": "antigravity",
            })
            packed = subprocess.run(
                [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "pack", "--profile", "grok",
                 "-y", "--lang", "en", "--output-dir", str(out)],
                cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)
            zips = list(out.glob("packages/Level_*.zip"))
            self.assertEqual(len(zips), 1)
            self.assertEqual(_manifest(zips[0])["profile"], "grok")

            dest_data = root / "dst-data"
            dest_ws = root / "dst-ws"
            (dest_data / "agents" / DST).mkdir(parents=True)
            (dest_data / "agents" / DST / "profile.json").write_text("KEEP", encoding="utf-8")
            (dest_data / "search-index.db").write_text("SENTINEL", encoding="utf-8")
            env.update({
                "GROK_AGENT_DATA": str(dest_data),
                "GROK_WORKSPACE": str(dest_ws),
            })
            restored = subprocess.run(
                [sys.executable, str(REPO / "workspace_toolkit.py"), "--mode", "restore",
                 "--input-dir", str(zips[0]), "--uuid-map", f"{SRC}={DST}",
                 "--target-env", "existing", "-y", "--lang", "en"],
                cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            self.assertEqual((dest_data / "agents" / DST / "profile.json").read_text(encoding="utf-8"), "KEEP")
            self.assertIn(DST, (dest_data / "agents" / DST / "profile.json.incoming").read_text(encoding="utf-8"))
            self.assertEqual((dest_data / "search-index.db").read_text(encoding="utf-8"), "SENTINEL")
            self.assertIn(DST, (dest_ws / "note.md").read_text(encoding="utf-8"))
            self.assertIn(DST, (dest_data / "workflows" / "demo" / "SKILL.md").read_text(encoding="utf-8"))
            self.assertTrue(list(dest_ws.glob(".grok-restore-incoming/*/MANUAL_REBUILD.md")))


if __name__ == "__main__":
    unittest.main()
