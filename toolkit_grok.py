"""Grok Bot environment profile.

Additive to the Antigravity scanner, packer, and restore path. Nothing here runs
unless the selected profile is ``grok`` (auto-detected when agent-data exists,
or forced with ``--profile grok`` / ``UAWT_PROFILE=grok``).

Layout notes (agent ids, memory-drop JSONL, user workflows versus managed and
plugin skills, and a read-only SQLite backup of search-index.db) follow the
public Grok Bot box shape. See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from toolkit_scanner import (
    EXCLUDED_DIRS,
    HIGH_CONF_RE,
    PRIVATE_KEY_RE,
    calculate_sha256,
    classify_file,
    redact_mcp_json,
    win_p,
)

L1 = "Level_1_Agent_Directives"
L2 = "Level_2_System_Settings"
L3 = "Level_3_Modular_Skills"
L4 = "Level_4_Workspace_Docs"
L5 = "Level_5_Heavy_References"
L6 = "Level_6_Memory_Drop"
L7 = "Level_7_Conversations"
L8 = "Level_8_Cursor_Stores_Experimental"
LEVEL_ORDER = (L1, L2, L3, L4, L5, L6, L7, L8)

# Packed even when they are large: identity, user skills, memory, conversations, opt-in stores.
NEVER_DEMOTE = {L1, L3, L6, L7, L8}
HEAVY_SUFFIXES = {".mp4", ".mov", ".avi", ".iso", ".dmg", ".tar", ".gz"}
DIRECTIVE_NAMES = {"AGENTS.md", "CLAUDE.md", ".cursorrules", ".clinerules"}
TEXT_SUFFIXES = {
    ".md", ".json", ".yaml", ".yml", ".py", ".txt", ".jsonl", ".toml",
    ".csv", ".html", ".xml", ".ini", ".cfg", ".rst", ".sh",
}
GROK_SECRET_FILENAMES = {
    "box-secrets.json",
    "host-secrets.json",
    "chrome-cookie-seed.json",
    "gateway.json",
    "teach-queue-key.json",
}
SKIP_DIR_NAMES = set(EXCLUDED_DIRS) | {"managed-skills", "plugin-skills", ".cache"}
AGENT_ID_RE = re.compile(
    r"^(?:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32})$"
)
USER_CONTENT_TOPS = {"notes", "reference", "attachments", "private"}


class GrokError(Exception):
    """The Grok profile was selected but the request cannot be completed."""


def valid_agent_id(value):
    return isinstance(value, str) and bool(AGENT_ID_RE.fullmatch(value))


def grok_paths(env=None):
    """Resolve Grok locations. Explicit GROK_* variables win, then the names used by grok-bot-backup."""
    env = os.environ if env is None else env
    workspace = Path(env.get("GROK_WORKSPACE") or env.get("WORKSPACE") or "/workspace")
    agent_data = Path(env.get("GROK_AGENT_DATA") or env.get("AGENT_DATA") or "/home/box/agent-data")
    memory_drop = Path(
        env.get("GROK_MEMORY_DROP")
        or env.get("MEMORY_DROP")
        or (workspace / "exports" / "memory-drop")
    )
    cursor_stores = Path(env.get("GROK_CURSOR_STORES") or "/cursor/stores")
    return {
        "agent_data": agent_data,
        "workspace": workspace,
        "memory_drop": memory_drop,
        "cursor_stores": cursor_stores,
        "search_index": agent_data / "search-index.db",
    }


def detect_profile(explicit=None, env=None):
    """Return ``antigravity`` or ``grok``.

    ``auto`` (the default) is Grok only when the agent-data directory exists.
    A machine without that directory keeps the Antigravity path, including when
    ``/workspace`` exists for some other reason.
    """
    env = os.environ if env is None else env
    choice = (explicit or env.get("UAWT_PROFILE") or "auto").strip().lower()
    if choice in ("antigravity", "grok"):
        return choice
    if choice != "auto":
        raise GrokError("profile must be auto, antigravity, or grok")
    if grok_paths(env)["agent_data"].is_dir():
        return "grok"
    return "antigravity"


def grok_secret_reason(path, agent_data):
    """Filename rules that apply only to the Grok profile."""
    name = Path(path).name.lower()
    if name in GROK_SECRET_FILENAMES:
        return f"Grok platform secret ({Path(path).name})"
    try:
        rel = Path(path).resolve().relative_to(Path(agent_data).resolve())
    except (ValueError, OSError):
        return None
    if len(rel.parts) == 1 and name.endswith("-secrets.json"):
        return f"top-level agent-data secrets file ({Path(path).name})"
    return None


def _under(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def _display(path, paths):
    path = Path(path)
    pairs = (
        (paths.get("workspace"), "workspace"),
        (paths.get("agent_data"), "agent-data"),
        (paths.get("memory_drop"), "memory-drop"),
        (paths.get("cursor_stores"), "cursor-stores"),
    )
    for root, label in pairs:
        if root and _under(path, root):
            rel = path.resolve().relative_to(Path(root).resolve()).as_posix()
            return f"{label}/{rel}" if rel else label
    return str(path)


def _heavy(path, size):
    if size / (1024 * 1024) > 10.0:
        return True
    return Path(path).suffix.lower() in HEAVY_SUFFIXES


def _skip_dir_reason(full, name, include_bulky, include_subagents, exclude_roots):
    if full.is_symlink():
        return "symlink (not followed)"
    if name in SKIP_DIR_NAMES or name in {"managed-skills", "plugin-skills"}:
        if name in {"managed-skills", "plugin-skills"}:
            return "platform-managed skills are not user workflows"
        return "excluded directory"
    if name == ".grok-restore-incoming" or name.startswith(".grok-pre-restore-snapshot_"):
        return "restore bookkeeping"
    if name == "migration_output":
        return "toolkit output directory"
    if name.startswith(("grok-bot-export-", "virtual-office-")):
        return "previous backup artifact"
    if not include_subagents and name.startswith("sand-subagent-"):
        return "sand-subagent transcript (pass --include-subagents to pack)"
    if not include_bulky and name.startswith(".venv"):
        return "bulky directory"
    for root in exclude_roots:
        if root and _under(full, root):
            return "excluded root"
    return None


def _iter_files(root, include_bulky, include_subagents, exclude_roots, skipped):
    root = Path(root)
    if not root.exists():
        return
    if root.is_file():
        if not root.is_symlink():
            yield root
        else:
            skipped.append((root, "symlink (not followed)"))
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        kept = []
        for name in list(dirnames):
            full = Path(dirpath) / name
            reason = _skip_dir_reason(full, name, include_bulky, include_subagents, exclude_roots)
            if reason:
                skipped.append((full, reason))
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                skipped.append((full, "symlink (not followed)"))
                continue
            if name.startswith(("grok-bot-export-", "virtual-office-")) and name.endswith(
                (".tar", ".tar.gz", ".tgz", ".zip", ".zip.enc")
            ):
                skipped.append((full, "previous backup artifact"))
                continue
            yield full


def _load_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _jsonl_stats(path):
    facts = invalid = lines = 0
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                lines += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    invalid += 1
                    continue
                if isinstance(obj, dict) and str(obj.get("fact") or "").strip():
                    facts += 1
                else:
                    invalid += 1
    except OSError:
        invalid += 1
    return {"lines": lines, "facts": facts, "invalid": invalid}


def _empty_assets(paths, include_secrets):
    return {
        "profile": "grok",
        "paths": paths,
        "include_secrets": include_secrets,
        "files": [],
        "excluded": [],
        "flagged": [],
        "skipped": [],
        "warnings": [],
        "redacted": [],
        "agents": [],
        "skills_names": [],
        "memory": {},
        "experimental": {},
        "sizes_mb": {level: 0.0 for level in LEVEL_ORDER},
        "t_core_mb": 0.0,
        "seen": set(),
    }


def _add_file(assets, fp, level, arc, include_secrets, include_cursor_payload=False):
    fp = Path(fp)
    paths = assets["paths"]
    key = (level, arc)
    if key in assets["seen"] or arc in {item[1] for item in assets["seen"]}:
        assets["skipped"].append((fp, "duplicate archive path"))
        return
    if not include_secrets:
        reason = grok_secret_reason(fp, paths["agent_data"])
        if reason:
            assets["excluded"].append((fp, reason))
            return
    payload = None
    redacted = False
    if not include_secrets and fp.suffix.lower() == ".json":
        try:
            text = fp.read_text(encoding="utf-8")
            new_text, count = redact_mcp_json(text)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            new_text, count = None, 0
        if count and new_text is not None:
            if PRIVATE_KEY_RE.search(new_text) or HIGH_CONF_RE.search(new_text):
                assets["excluded"].append((fp, "still contains a secret after JSON redaction"))
                return
            payload = new_text.encode("utf-8")
            redacted = True
            assets["redacted"].append(fp)
            assets["flagged"].append((fp, "secret JSON values replaced"))
    if not include_secrets and not redacted:
        verdict, reason = classify_file(fp, content_scan=True)
        if verdict == "exclude":
            assets["excluded"].append((fp, reason))
            return
        if verdict == "warn":
            assets["flagged"].append((fp, reason))
    try:
        size = len(payload) if payload is not None else fp.stat().st_size
    except OSError:
        assets["skipped"].append((fp, "unreadable"))
        return
    if level not in NEVER_DEMOTE and _heavy(fp, size):
        level = L5
    assets["seen"].add((level, arc))
    assets["files"].append({
        "src": fp,
        "level": level,
        "arc": arc,
        "size": size,
        "payload": payload,
        "redacted": redacted,
    })


def _collect_agent(assets, agent_dir, include_secrets, include_bulky, include_subagents, exclude_roots):
    aid = agent_dir.name
    profile = _load_json(agent_dir / "profile.json") or {}
    kind = "group" if (agent_dir / "group.json").exists() else "agent"
    name = profile.get("name") or aid
    assets["agents"].append({"id": aid, "name": name, "kind": kind})
    for fp in _iter_files(agent_dir, include_bulky, include_subagents, exclude_roots, assets["skipped"]):
        rel = fp.relative_to(agent_dir).as_posix()
        top = rel.split("/", 1)[0]
        if rel in {"profile.json", "group.json"} or Path(rel).name.startswith("avatar."):
            level, arc = L1, f"agents/{aid}/{rel}"
        elif rel == "settings.json" or top == "automations":
            level, arc = L2, f"agents/{aid}/{rel}"
        elif top in USER_CONTENT_TOPS:
            level, arc = L4, f"agents/{aid}/{rel}"
        elif top == "memory":
            tail = rel.split("/", 1)[1] if "/" in rel else rel
            level, arc = L6, f"local-agents/{aid}/{tail}"
        else:
            level, arc = L2, f"agents/{aid}/extra/{rel}"
        _add_file(assets, fp, level, arc, include_secrets)


def _summarize_memory(memory_root, agent_ids):
    report = {
        "drop_root": str(memory_root),
        "present": memory_root.is_dir(),
        "shared_user": None,
        "agents": [],
        "note": (
            "Memory-drop JSONL is exported by each bot. "
            "Copying the file does not recreate platform memory; import it on the target bot."
        ),
    }
    if not memory_root.is_dir():
        report["note"] = "memory-drop directory is absent; Level_6 will not contain a RecallMemory export"
        return report
    shared = memory_root / "shared-user"
    shared_files = sorted(p for p in shared.glob("*") if p.is_file()) if shared.is_dir() else []
    if shared_files or (shared / "memory-status.json").is_file():
        stats = {}
        for fp in shared_files:
            if fp.suffix.lower() == ".jsonl":
                stats[fp.name] = _jsonl_stats(fp)
        report["shared_user"] = {"files": stats, "explicit_empty": (shared / "memory-status.json").is_file()}
    known = set(agent_ids)
    agents_root = memory_root / "agents"
    found = set()
    if agents_root.is_dir():
        for directory in sorted(p for p in agents_root.iterdir() if p.is_dir() and not p.is_symlink()):
            files = {}
            for fp in sorted(directory.glob("*.jsonl")):
                files[fp.name] = _jsonl_stats(fp)
            status = directory / "memory-status.json"
            report["agents"].append({
                "id": directory.name,
                "files": files,
                "explicit_empty": status.is_file(),
                "in_roster": directory.name in known,
            })
            found.add(directory.name)
    for aid in agent_ids:
        if aid not in found:
            report["agents"].append({
                "id": aid, "files": {}, "explicit_empty": False, "in_roster": True, "dropped": False,
            })
    return report


def list_cursor_stores(root):
    """Names and sizes only. This host layout was not verified as Grok Bot Pages."""
    root = Path(root)
    info = {
        "status": "experimental",
        "experimental": True,
        "verified": False,
        "packed": False,
        "note": (
            "Experimental: /cursor/stores entries are listed only. "
            "The Pages/canvas layout was not verified against a live Grok Bot host. "
            "Contents are packed only with --include-cursor-stores and are never written "
            "back into the stores directory on restore."
        ),
        "root": str(root),
        "entries": [],
    }
    if not root.exists():
        info["status"] = "absent"
        return info
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        info["status"] = "unreadable"
        info["error"] = str(exc)
        return info
    for child in children:
        if child.is_symlink():
            try:
                target = os.readlink(child)
            except OSError:
                target = ""
            info["entries"].append({"name": child.name, "kind": "symlink", "target": target})
            continue
        if not child.is_dir():
            try:
                size = child.stat().st_size
            except OSError:
                size = 0
            info["entries"].append({"name": child.name, "kind": "file", "files": 1, "bytes": size})
            continue
        files = nbytes = 0
        for dirpath, dirnames, filenames in os.walk(child, followlinks=False):
            dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]
            for filename in filenames:
                fp = Path(dirpath) / filename
                if fp.is_symlink():
                    continue
                files += 1
                try:
                    nbytes += fp.stat().st_size
                except OSError:
                    pass
        info["entries"].append({"name": child.name, "kind": "dir", "files": files, "bytes": nbytes})
    return info


def scan_grok_assets(paths, include_secrets=False, include_cursor_stores=False,
                     include_subagents=False, include_bulky=False, exclude_roots=None):
    """Classify a Grok Bot box into Level_1..Level_8. Does not read Antigravity directories."""
    paths = dict(paths)
    agent_data = Path(paths["agent_data"])
    if not agent_data.is_dir():
        raise GrokError(
            f"Grok Bot profile selected, but agent-data was not found at {agent_data}. "
            "Set GROK_AGENT_DATA or AGENT_DATA."
        )
    assets = _empty_assets(paths, include_secrets)
    exclude_roots = [Path(p) for p in (exclude_roots or []) if p]
    memory_root = Path(paths["memory_drop"])
    workspace = Path(paths["workspace"])
    # Keep the drop out of the workspace copy when it lives inside the workspace; it is packed as Level_6.
    if memory_root.exists() and memory_root.resolve() != workspace.resolve() and not _under(workspace, memory_root):
        exclude_roots.append(memory_root)

    if not workspace.is_dir():
        assets["warnings"].append(f"workspace directory not found: {workspace}")
    else:
        for fp in _iter_files(workspace, include_bulky, include_subagents, exclude_roots, assets["skipped"]):
            rel = fp.relative_to(workspace).as_posix()
            if fp.name in DIRECTIVE_NAMES:
                _add_file(assets, fp, L1, f"workspace/{rel}", include_secrets)
            else:
                _add_file(assets, fp, L4, f"workspace/{rel}", include_secrets)

    agents_root = agent_data / "agents"
    if agents_root.is_dir():
        for child in sorted(agents_root.iterdir(), key=lambda p: p.name):
            if child.is_symlink():
                assets["skipped"].append((child, "symlink (not followed)"))
                continue
            if child.is_file():
                _add_file(assets, child, L2, f"platform/{child.name}", include_secrets)
                continue
            if not child.is_dir():
                continue
            is_agent = valid_agent_id(child.name) and any(
                (child / name).exists() for name in ("profile.json", "settings.json", "group.json")
            )
            if is_agent:
                _collect_agent(assets, child, include_secrets, include_bulky, include_subagents, exclude_roots)
            else:
                for fp in _iter_files(child, include_bulky, include_subagents, exclude_roots, assets["skipped"]):
                    rel = fp.relative_to(child).as_posix()
                    _add_file(assets, fp, L2, f"platform/{child.name}/{rel}", include_secrets)

    workflows = agent_data / "workflows"
    if workflows.is_dir():
        names = set()
        for fp in _iter_files(workflows, include_bulky, include_subagents, exclude_roots, assets["skipped"]):
            rel = fp.relative_to(workflows).as_posix()
            if rel.split("/", 1)[0] not in names and "/" in rel:
                names.add(rel.split("/", 1)[0])
            elif "/" not in rel:
                names.add(rel)
            _add_file(assets, fp, L3, rel, include_secrets)
        assets["skills_names"] = sorted(names)

    projects = agent_data / "projects"
    if projects.is_dir():
        for fp in _iter_files(projects, include_bulky, include_subagents, exclude_roots, assets["skipped"]):
            rel = fp.relative_to(projects).as_posix()
            _add_file(assets, fp, L4, f"shared/projects/{rel}", include_secrets)

    user_memory = agent_data / "user-memory"
    if user_memory.is_dir():
        for fp in _iter_files(user_memory, include_bulky, include_subagents, exclude_roots, assets["skipped"]):
            rel = fp.relative_to(user_memory).as_posix()
            _add_file(assets, fp, L6, f"user-memory/{rel}", include_secrets)

    # Top-level secret files must show up in the Level_0 report even if nothing else at the root is packed.
    try:
        root_entries = list(agent_data.iterdir())
    except OSError:
        root_entries = []
    for child in root_entries:
        if child.is_file() and grok_secret_reason(child, agent_data):
            _add_file(assets, child, L2, f"platform-secrets/{child.name}", include_secrets)

    transcripts = agent_data / "agent-transcripts"
    if transcripts.is_dir():
        for fp in _iter_files(transcripts, include_bulky, include_subagents, exclude_roots, assets["skipped"]):
            rel = fp.relative_to(transcripts).as_posix()
            _add_file(assets, fp, L7, f"agent-transcripts/{rel}", include_secrets)

    if Path(paths["search_index"]).is_file():
        assets["search_index"] = Path(paths["search_index"])
    else:
        assets["search_index"] = None
        assets["warnings"].append(f"search-index.db not found at {paths['search_index']}")

    if memory_root.is_dir():
        for fp in _iter_files(memory_root, True, True, [], assets["skipped"]):
            rel = fp.relative_to(memory_root).as_posix()
            _add_file(assets, fp, L6, rel, include_secrets)
    assets["memory"] = _summarize_memory(memory_root, [a["id"] for a in assets["agents"]])

    assets["experimental"] = {"cursor_stores": list_cursor_stores(paths["cursor_stores"])}
    if include_cursor_stores and Path(paths["cursor_stores"]).is_dir():
        assets["experimental"]["cursor_stores"]["packed"] = True
        for fp in _iter_files(paths["cursor_stores"], include_bulky, include_subagents, [], assets["skipped"]):
            rel = fp.relative_to(paths["cursor_stores"]).as_posix()
            _add_file(assets, fp, L8, rel, include_secrets)

    for level in LEVEL_ORDER:
        assets["sizes_mb"][level] = sum(item["size"] for item in assets["files"] if item["level"] == level) / (1024 * 1024)
    assets["t_core_mb"] = sum(assets["sizes_mb"][level] for level in (L1, L2, L3))
    return assets


def _record(staging_dir, path, level_number, file_manifest):
    rel = path.relative_to(staging_dir).as_posix()
    file_manifest[rel] = {"size": path.stat().st_size, "sha256": calculate_sha256(path), "level": level_number}
    return rel


def _write_record(src, payload, dest, staging_dir, level_number, file_manifest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if payload is not None:
        dest.write_bytes(payload)
    else:
        shutil.copy2(win_p(src), win_p(dest))
    return _record(staging_dir, dest, level_number, file_manifest)


def _snapshot_sqlite(src, dest):
    """Consistent snapshot via sqlite3 backup. Returns (ok, consistent, error)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        if os.name != "nt":
            uri = "file:" + quote(Path(src).resolve().as_posix()) + "?mode=ro"
            src_conn = sqlite3.connect(uri, uri=True)
        else:
            src_conn = sqlite3.connect(src)
        dst_conn = sqlite3.connect(dest)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
        return True, True, ""
    except sqlite3.Error as exc:
        try:
            if dest.exists():
                dest.unlink()
            shutil.copy2(src, dest)
            return True, False, str(exc)
        except OSError as copy_exc:
            return False, False, f"{exc}; {copy_exc}"


def _message_counts(db_path):
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return {}
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        if "messages" not in tables:
            return {}
        rows = conn.execute("select agent_id, count(*) from messages group by agent_id").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return {str(agent_id): count for agent_id, count in rows if agent_id is not None}


def run_grok_pack(assets, output_base, user_home, encrypted=False):
    """Pack a scanned Grok box. Level_5 is inventoried and not written into the zip."""
    include_secrets = assets["include_secrets"]
    now = datetime.now()
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    tracking_id = f"PKG-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"
    output_base = Path(output_base)
    packages_dir = output_base / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_base / f"_staging_{ts_str}"
    if staging_dir.exists():
        shutil.rmtree(win_p(staging_dir), ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    paths = assets["paths"]

    try:
        file_manifest = {}
        level_counts = {level: 0 for level in LEVEL_ORDER}
        level5 = []
        redacted = []
        for item in assets["files"]:
            level = item["level"]
            if level == L5:
                level_counts[L5] += 1
                level5.append({
                    "path": _display(item["src"], paths),
                    "bytes": item["size"],
                    "arc": item["arc"],
                })
                continue
            dest = staging_dir / level / item["arc"]
            rel = _write_record(item["src"], item.get("payload"), dest, staging_dir, LEVEL_ORDER.index(level) + 1, file_manifest)
            level_counts[level] += 1
            if item.get("redacted"):
                redacted.append(rel)

        conversations = {
            "read_only": True,
            "source": str(paths["search_index"]),
            "snapshot": None,
            "consistent_snapshot": None,
            "agents": [],
            "platform_message_rows": 0,
            "note": (
                "search-index-snapshot.db is a read-only copy. "
                "Restore must not replace the live search-index.db or live agent-transcripts."
            ),
        }
        search_index = assets.get("search_index")
        if search_index and Path(search_index).is_file():
            snap_path = staging_dir / L7 / "search-index-snapshot.db"
            ok, consistent, error = _snapshot_sqlite(search_index, snap_path)
            conversations["consistent_snapshot"] = consistent
            if error:
                conversations["snapshot_error"] = error
            if ok and snap_path.is_file():
                rel = _record(staging_dir, snap_path, 7, file_manifest)
                conversations["snapshot"] = rel
                level_counts[L7] += 1
                counts = _message_counts(snap_path)
                named = {agent["id"]: agent for agent in assets["agents"]}
                platform_rows = 0
                listed = []
                for agent_id, count in sorted(counts.items()):
                    if agent_id in named or valid_agent_id(agent_id):
                        meta = named.get(agent_id, {"id": agent_id, "name": agent_id, "kind": "unknown"})
                        listed.append({
                            "id": meta["id"], "name": meta["name"], "kind": meta["kind"], "messages": count,
                        })
                    else:
                        platform_rows += count
                for agent in assets["agents"]:
                    if agent["id"] not in counts:
                        listed.append({
                            "id": agent["id"], "name": agent["name"], "kind": agent["kind"], "messages": 0,
                        })
                conversations["agents"] = listed
                conversations["platform_message_rows"] = platform_rows
                stats_path = staging_dir / L7 / "conversation-stats.json"
                stats_path.write_text(json.dumps({
                    "read_only": True,
                    "source": conversations["source"],
                    "consistent_snapshot": consistent,
                    "agents": listed,
                    "platform_message_rows": platform_rows,
                }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                _record(staging_dir, stats_path, 7, file_manifest)
                level_counts[L7] += 1

        excluded = [{"path": _display(p, paths), "reason": r} for p, r in assets["excluded"]]
        flagged = [{"path": _display(p, paths), "reason": r} for p, r in assets["flagged"]]
        skipped = [{"path": _display(p, paths), "reason": r} for p, r in assets["skipped"]]
        has_level8 = level_counts[L8] > 0
        zip_filename = (
            f"Level_1_to_8_Grok_Bot_{ts_str}.zip" if has_level8 else f"Level_1_to_7_Grok_Bot_{ts_str}.zip"
        )
        zip_path = packages_dir / zip_filename
        total_size_mb = sum(item["size"] for item in file_manifest.values()) / (1024 * 1024)
        manifest_doc = {
            "manifest_version": "v2.2.0",
            "profile": "grok",
            "tracking_id": tracking_id,
            "created_at": now.isoformat(),
            "include_secrets": include_secrets,
            "encrypted": encrypted,
            "sender_system": {
                "machine_fingerprint": platform.node(),
                "os": sys.platform,
                "os_release": platform.release(),
                "user": Path(user_home).name,
                "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "profile": "grok",
                "skills_count": len(assets["skills_names"]),
                "agents": assets["agents"],
            },
            "grok_paths": {key: str(value) for key, value in paths.items()},
            "cargo_levels": {level: {"count": level_counts[level]} for level in LEVEL_ORDER},
            "excluded": excluded,
            "redacted": redacted,
            "flagged": flagged,
            "skipped": skipped,
            "level5_omitted": level5,
            "memory_drop": assets["memory"],
            "conversations": conversations,
            "experimental": assets["experimental"],
            "warnings": list(assets["warnings"]),
            "restore_policy": {
                "direct": [
                    "Level_4 paths under workspace/ restore into the target workspace",
                    "Level_3 user workflows restore into <agent-data>/workflows",
                ],
                "incoming_only": [
                    "profile, settings, avatar, group, routines, memory-drop, notes, reference, attachments, private, projects",
                ],
                "never_overwrite": [
                    "live search-index.db",
                    "live agent-transcripts",
                    "live profile.json / settings.json / automations",
                    "/cursor/stores",
                ],
            },
            "file_manifest": file_manifest,
        }
        (staging_dir / "package_manifest.json").write_text(
            json.dumps(manifest_doc, indent=2, ensure_ascii=False), encoding="utf-8")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for dirpath, _, filenames in os.walk(staging_dir):
                for filename in filenames:
                    fp = Path(dirpath) / filename
                    zipf.write(win_p(fp), arcname=fp.relative_to(staging_dir).as_posix())
        with zipfile.ZipFile(zip_path, "r") as zipf:
            names = set(zipf.namelist())
            for rel in file_manifest:
                if rel not in names:
                    raise RuntimeError(f"Integrity check failed: missing {rel} in zip")
        try:
            os.chmod(zip_path, 0o600)
        except OSError:
            pass
    finally:
        shutil.rmtree(win_p(staging_dir), ignore_errors=True)

    return {
        "zip_path": zip_path,
        "tracking_id": tracking_id,
        "total_files": len(file_manifest),
        "total_size_mb": round(total_size_mb, 2),
        "level_counts": level_counts,
        "excluded": excluded,
        "redacted": redacted,
        "flagged": flagged,
        "warnings": list(assets["warnings"]),
        "memory": assets["memory"],
        "conversations": conversations,
        "experimental": assets["experimental"],
    }


def parse_uuid_map(pairs=None, map_file=None):
    """Return ``{old_lower: new_lower}``. Identity pairs are dropped."""
    raw = {}
    if map_file:
        data = json.loads(Path(map_file).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise GrokError("uuid map file must be a JSON object of old id to new id")
        for key, value in data.items():
            raw[str(key).strip()] = str(value).strip()
    for item in pairs or []:
        if "=" not in item:
            raise GrokError(f"uuid map entry must be OLD=NEW, got {item!r}")
        old, new = item.split("=", 1)
        raw[old.strip()] = new.strip()
    mapped = {}
    for old, new in raw.items():
        if not valid_agent_id(old) or not valid_agent_id(new):
            raise GrokError(f"uuid map values must be agent ids: {old} -> {new}")
        if old.lower() == new.lower():
            continue
        mapped[old.lower()] = new.lower()
    return mapped


def _split_rel(rel):
    rel = rel.replace("\\", "/")
    level, sep, arc = rel.partition("/")
    if not sep:
        return rel, ""
    return level, arc


def _mapped_id(agent_id, uuid_map):
    return uuid_map.get(str(agent_id).lower(), agent_id)


def _remap_arc(arc, uuid_map):
    parts = arc.split("/")
    if len(parts) > 1 and parts[0] in {"agents", "local-agents", "agent-transcripts"} and valid_agent_id(parts[1]):
        parts[1] = _mapped_id(parts[1], uuid_map)
    return "/".join(parts)


def _sidecar_destination(level, arc, agent_data, uuid_map):
    """A ``*.incoming`` path inside an existing platform directory, or None.

    Missing agent directories are not created. Live filenames are not returned.
    """
    if not agent_data or not Path(agent_data).is_dir():
        return None
    agent_data = Path(agent_data)
    parts = arc.split("/")
    if level == L6 and len(parts) == 2 and parts[0] == "shared-user":
        user_memory = agent_data / "user-memory"
        if user_memory.is_dir():
            return user_memory / f"{parts[1]}.incoming"
        return None
    if len(parts) < 3 or parts[0] != "agents" or not valid_agent_id(parts[1]):
        return None
    aid = _mapped_id(parts[1], uuid_map)
    rest = "/".join(parts[2:])
    base = agent_data / "agents" / aid
    if not base.is_dir():
        return None
    name = PurePosixPath(rest).name
    if rest in {"profile.json", "settings.json", "group.json"} or name.startswith("avatar."):
        return base / f"{name}.incoming"
    if rest.startswith("automations/"):
        automations = base / "automations"
        if not automations.is_dir():
            return None
        tail = rest[len("automations/"):]
        return automations / f"{tail}.incoming"
    if level == L6 and "/" not in rest:
        return base / f"{rest}.incoming"
    return None


def build_restore_plan(staging_dir, manifest, dest_paths, target_env, uuid_map):
    """Describe every write. Platform-managed files land in the incoming kit, not on live names."""
    staging_dir = Path(staging_dir)
    workspace = Path(dest_paths["workspace"])
    agent_data = Path(dest_paths["agent_data"])
    tracking_id = manifest.get("tracking_id") or "restore"
    kit = workspace / ".grok-restore-incoming" / tracking_id
    actions = []
    for rel in manifest.get("file_manifest", {}):
        if ".." in Path(rel).parts:
            continue
        src = staging_dir / rel
        try:
            src_resolved = src.resolve()
            if staging_dir.resolve() not in src_resolved.parents:
                continue
        except OSError:
            continue
        if not src.is_file():
            continue
        level, arc = _split_rel(rel)
        if level not in LEVEL_ORDER or not arc:
            continue
        mapped_arc = _remap_arc(arc, uuid_map)

        def add(kind, dest, snapshot=True):
            actions.append({
                "kind": kind,
                "src": src,
                "dest": Path(dest),
                "snapshot": snapshot,
                "remap": True,
                "level": level,
                "arc": arc,
            })

        if level == L3:
            if agent_data.is_dir():
                add("workflow", agent_data / "workflows" / mapped_arc)
            else:
                add("incoming", kit / level / mapped_arc, snapshot=True)
            continue
        if arc.startswith("workspace/") and level == L4:
            add("workspace", workspace / arc[len("workspace/"):])
            continue
        if arc.startswith("workspace/") and level == L1:
            target = workspace / arc[len("workspace/"):]
            if target_env == "fresh":
                add("directive", target)
            else:
                add("directive", target.with_name(target.name + ".incoming"))
            add("incoming", kit / level / mapped_arc, snapshot=True)
            continue
        add("incoming", kit / level / mapped_arc, snapshot=True)
        if level == L8:
            continue
        sidecar = _sidecar_destination(level, arc, agent_data, uuid_map)
        if sidecar is not None:
            add("sidecar", sidecar)
    return {"actions": actions, "kit": kit, "tracking_id": tracking_id}


def summarize_plan(plan):
    actions = plan["actions"]
    collisions = []
    for action in actions:
        if action["kind"] in {"workspace", "workflow", "directive", "sidecar"} and action["dest"].exists():
            collisions.append(str(action["dest"]))
    return {
        "workspace_writes": sum(1 for a in actions if a["kind"] == "workspace"),
        "workflow_writes": sum(1 for a in actions if a["kind"] == "workflow"),
        "directive_writes": sum(1 for a in actions if a["kind"] == "directive"),
        "incoming_files": sum(1 for a in actions if a["kind"] == "incoming"),
        "sidecars": sum(1 for a in actions if a["kind"] == "sidecar"),
        "collisions": collisions,
        "kit": plan["kit"],
    }


def create_grok_snapshot(workspace, agent_data, actions):
    """Copy files the restore might overwrite. Returns the snapshot directory, or None."""
    workspace = Path(workspace)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = workspace / f".grok-pre-restore-snapshot_{stamp}"
    mapping = []
    seen = set()
    for action in actions:
        if not action.get("snapshot"):
            continue
        src = Path(action["dest"])
        if not src.exists() or src.is_symlink():
            continue
        key = str(src.resolve()) if src.exists() else str(src)
        if key in seen:
            continue
        seen.add(key)
        rel = _snapshot_rel(src, workspace, agent_data)
        dest = snap / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(win_p(src), win_p(dest), dirs_exist_ok=True)
        else:
            shutil.copy2(win_p(src), win_p(dest))
        mapping.append((src, dest))
    if not mapping:
        if snap.exists():
            shutil.rmtree(snap, ignore_errors=True)
        return None
    lines = ["Rollback: copy each snapshot item back over its original location.", ""]
    lines += [f"{dest}  ->  {src}" for src, dest in mapping]
    (snap / "ROLLBACK.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return snap


def _snapshot_rel(dest, workspace, agent_data):
    for label, root in (("workspace", workspace), ("agent-data", agent_data)):
        try:
            return Path(label) / Path(dest).resolve().relative_to(Path(root).resolve())
        except (ValueError, OSError):
            continue
    return Path("other") / Path(dest).name


def _apply_replacements(text, replacements):
    usable = [(old, new) for old, new in replacements if old and old != new]
    if not usable or not text:
        return text
    usable.sort(key=lambda pair: len(pair[0]), reverse=True)
    pattern = re.compile("|".join(re.escape(old) for old, _ in usable))
    table = {old: new for old, new in usable}
    return pattern.sub(lambda match: table[match.group(0)], text)


def _apply_uuid_map(text, uuid_map):
    if not uuid_map or not text:
        return text
    keys = sorted(uuid_map, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(key) for key in keys), re.IGNORECASE)
    return pattern.sub(lambda match: uuid_map[match.group(0).lower()], text)


def path_replacements(manifest, user_home, dest_workspace, dest_agent_data):
    sender = manifest.get("sender_system") or {}
    grok = manifest.get("grok_paths") or {}
    src_user = sender.get("user") or ""
    reps = []
    src_ws = str(grok.get("workspace") or "")
    src_agent = str(grok.get("agent_data") or "")
    dest_ws = str(dest_workspace)
    dest_agent = str(dest_agent_data)
    if src_ws and src_ws.rstrip("/") != dest_ws.rstrip("/"):
        reps.append((src_ws.rstrip("/"), dest_ws.rstrip("/")))
    if src_agent and src_agent.rstrip("/") != dest_agent.rstrip("/"):
        reps.append((src_agent.rstrip("/"), dest_agent.rstrip("/")))
    user_home = Path(user_home)
    if src_user and src_user != user_home.name:
        reps.extend([
            (f"file:///C:/Users/{src_user}/", f"file:///{user_home.as_posix()}/"),
            (f"file:///C:/Users/{src_user.replace(' ', '%20')}/", f"file:///{user_home.as_posix().replace(' ', '%20')}/"),
            (f"C:/Users/{src_user}/", f"{user_home.as_posix()}/"),
            (f"/Users/{src_user}/", f"/Users/{user_home.name}/"),
            (f"/home/{src_user}/", f"/home/{user_home.name}/"),
        ])
    return reps


def _is_text_source(path):
    return Path(path).suffix.lower() in TEXT_SUFFIXES


def _chmod_tree(root):
    root = Path(root)
    if not root.exists():
        return
    try:
        if root.is_file():
            os.chmod(root, 0o600)
            return
        for dirpath, _, filenames in os.walk(root):
            try:
                os.chmod(dirpath, 0o700)
            except OSError:
                pass
            for filename in filenames:
                fp = Path(dirpath) / filename
                if not fp.is_symlink():
                    try:
                        os.chmod(fp, 0o600)
                    except OSError:
                        pass
    except OSError:
        pass


def execute_grok_restore(plan, manifest, user_home, dest_paths, uuid_map, lang="en"):
    """Write workspace files and user skills. Everything else stays in the incoming kit or a sidecar."""
    workspace = Path(dest_paths["workspace"])
    agent_data = Path(dest_paths["agent_data"])
    workspace.mkdir(parents=True, exist_ok=True)
    if any(action["kind"] == "workflow" for action in plan["actions"]) and agent_data.is_dir():
        (agent_data / "workflows").mkdir(parents=True, exist_ok=True)
    replacements = path_replacements(manifest, user_home, workspace, agent_data)
    refactored = 0
    written = []
    for action in plan["actions"]:
        dest = Path(action["dest"])
        # Never replace a live platform file. Sidecar names already end with .incoming.
        if action["kind"] == "sidecar" and not dest.name.endswith(".incoming"):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        changed = _write_mapped(action["src"], dest, replacements, uuid_map, action.get("remap", True))
        if changed:
            refactored += 1
        written.append(dest)
        if action["kind"] in {"incoming", "sidecar"}:
            try:
                os.chmod(dest, 0o600)
            except OSError:
                pass
    kit = Path(plan["kit"])
    checklist = kit / "MANUAL_REBUILD.md"
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(build_checklist(lang, {
        "tracking_id": plan["tracking_id"],
        "workspace": workspace,
        "agent_data": agent_data,
        "kit": kit,
        "uuid_map": uuid_map,
        "agents": (manifest.get("sender_system") or {}).get("agents") or [],
        "actions": plan["actions"],
        "excluded": manifest.get("excluded") or [],
        "redacted": manifest.get("redacted") or [],
        "level5": manifest.get("level5_omitted") or [],
        "memory": manifest.get("memory_drop") or {},
        "conversations": manifest.get("conversations") or {},
        "experimental": manifest.get("experimental") or {},
        "skills_direct": any(action["kind"] == "workflow" for action in plan["actions"]),
        "agent_data_present": agent_data.is_dir(),
    }), encoding="utf-8")
    _chmod_tree(kit)
    return {
        "workspace": workspace,
        "workflows": agent_data / "workflows",
        "incoming_dir": kit,
        "checklist": checklist,
        "refactored_count": refactored,
        "written": written,
        "sidecars": [action["dest"] for action in plan["actions"] if action["kind"] == "sidecar"],
    }


def _write_mapped(src, dest, replacements, uuid_map, remap):
    if not remap or not _is_text_source(src):
        shutil.copy2(win_p(src), win_p(dest))
        return False
    try:
        text = Path(src).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        shutil.copy2(win_p(src), win_p(dest))
        return False
    new = _apply_uuid_map(_apply_replacements(text, replacements), uuid_map)
    dest.write_text(new, encoding="utf-8")
    return new != text


def build_checklist(lang, ctx):
    texts = _CHECKLIST.get(lang, _CHECKLIST["en"])
    agents = []
    for agent in ctx["agents"]:
        source = agent.get("id", "")
        target = ctx["uuid_map"].get(str(source).lower(), source)
        agents.append(f"- {agent.get('name') or source} ({agent.get('kind') or 'agent'}): `{source}` -> `{target}`")
    uuid_lines = [f"- `{old}` -> `{new}`" for old, new in sorted(ctx["uuid_map"].items())] or [texts["no_uuid"]]
    excluded = [f"- {item.get('path')}: {item.get('reason')}" for item in ctx["excluded"][:40]] or [texts["none"]]
    level5 = [f"- {item.get('path')} ({item.get('bytes')} bytes)" for item in ctx["level5"][:40]] or [texts["none"]]
    stores = (ctx["experimental"].get("cursor_stores") or {})
    store_lines = [f"- {entry.get('name')} ({entry.get('kind')})" for entry in stores.get("entries") or []] or [texts["none"]]
    sidecar_n = sum(1 for action in ctx["actions"] if action["kind"] == "sidecar")
    workspace_n = sum(1 for action in ctx["actions"] if action["kind"] == "workspace")
    workflow_n = sum(1 for action in ctx["actions"] if action["kind"] == "workflow")
    lines = [
        texts["title"].format(tracking=ctx["tracking_id"]),
        "",
        texts["intro"],
        "",
        texts["auto_h"],
        texts["auto"].format(workspace=ctx["workspace"], workspace_n=workspace_n,
                             workflows=ctx["agent_data"] / "workflows", workflow_n=workflow_n,
                             skills_note="" if ctx["skills_direct"] else texts["skills_held"]),
        "",
        texts["not_h"],
        texts["not_body"],
        "",
        texts["uuid_h"],
        *uuid_lines,
        "",
        texts["agents_h"],
        *(agents or [texts["none"]]),
        "",
        texts["profile_h"],
        texts["profile_body"].format(sidecars=sidecar_n, kit=ctx["kit"]),
        "",
        texts["memory_h"],
        texts["memory_body"].format(root=ctx["memory"].get("drop_root", "")),
        "",
        texts["conv_h"],
        texts["conv_body"],
        "",
        texts["content_h"],
        texts["content_body"].format(kit=ctx["kit"]),
        "",
        texts["secrets_h"],
        *excluded,
        "",
        texts["heavy_h"],
        *level5,
        "",
        texts["stores_h"],
        texts["stores_body"],
        *store_lines,
        "",
        texts["skills_gap_h"],
        texts["skills_gap_body"],
        "",
        texts["footer"],
        "",
    ]
    return "\n".join(lines)


_CHECKLIST = {
    "en": {
        "title": "# Grok Bot manual rebuild ({tracking})",
        "intro": "This restore wrote workspace files and user skills only. Profile, settings, routines, memory, and conversations were not written over live platform data.",
        "auto_h": "## Written automatically",
        "auto": "- Workspace files ({workspace_n}) -> `{workspace}`\n- User skills ({workflow_n}) -> `{workflows}`{skills_note}",
        "skills_held": "\n- agent-data was missing, so skills were left in this folder instead of workflows/",
        "not_h": "## Not written on purpose",
        "not_body": "- Do not replace `search-index.db` with `search-index-snapshot.db`.\n- Do not replace live `agent-transcripts/`.\n- Do not copy `.incoming` files onto `profile.json`, `settings.json`, or routines until you have read them.\n- Do not copy anything into `/cursor/stores`.",
        "uuid_h": "## Bot id remap",
        "no_uuid": "- No uuid map was provided. Source ids are unchanged inside text files.",
        "agents_h": "## Bots in this package",
        "none": "- (none)",
        "profile_h": "## Profile, settings, routines",
        "profile_body": "{sidecars} sidecar file(s) ending in `.incoming` were written only where that bot directory (or its automations directory) already existed. The full copy is under `{kit}`. Review it, then rename a sidecar onto the live filename yourself if you want the bot to adopt it.",
        "memory_h": "## Memory",
        "memory_body": "Level_6 holds the memory-drop JSONL from `{root}` plus any local memory files. Placing those files on disk does not recreate RecallMemory. On the target bot, import each `fact` with the bot's own memory tool. An empty JSONL file is not proof the export ran; `memory-status.json` is only meaningful when that bot actually checked and found nothing.",
        "conv_h": "## Conversations (read-only)",
        "conv_body": "The search-index snapshot and transcripts are reference copies in this folder. Message bodies stay in the snapshot database; they were not loaded back into the live index. Text transcripts may have ids and paths rewritten. The database file itself is not rewritten.",
        "content_h": "## Notes, reference, attachments, private, projects",
        "content_body": "These are in `{kit}` under their level directories, with bot ids remapped in the folder names when a uuid map was given. Copy the pieces you still want into the matching bot directory yourself.",
        "secrets_h": "## Secrets left out of the package",
        "heavy_h": "## Heavy files counted but not packed (Level_5)",
        "stores_h": "## Pages / canvas stores (experimental)",
        "stores_body": "Listed only. This toolkit did not verify the live Pages layout, and restore did not write the stores directory.",
        "skills_gap_h": "## Skills the package does not contain",
        "skills_gap_body": "`managed-skills/` and `plugin-skills/` are host-provided and were not packed. Reinstall them on the target box if the bot needs them. Sand-subagent transcripts are omitted unless the package was built with `--include-subagents`.",
        "footer": "A rollback snapshot, when one was created, is a `.grok-pre-restore-snapshot_*` directory in the workspace. `ROLLBACK.txt` lists each saved file.",
    },
    "zh-tw": {
        "title": "# Grok Bot 手動重建清單 ({tracking})",
        "intro": "這次還原只寫入了工作區檔案與使用者技能。身份設定、例行工作、記憶與對話都沒有覆蓋平台正在使用的檔案。",
        "auto_h": "## 已自動寫入",
        "auto": "- 工作區檔案（{workspace_n}）-> `{workspace}`\n- 使用者技能（{workflow_n}）-> `{workflows}`{skills_note}",
        "skills_held": "\n- 目標沒有 agent-data，技能留在此資料夾，沒有寫入 workflows/。",
        "not_h": "## 故意沒有寫入",
        "not_body": "- 不要用 `search-index-snapshot.db` 覆蓋 live 的 `search-index.db`。\n- 不要覆蓋 live 的 `agent-transcripts/`。\n- 讀過內容之前，不要把 `.incoming` 蓋上 `profile.json`、`settings.json` 或例行工作。\n- 不要把任何檔案複製進 `/cursor/stores`。",
        "uuid_h": "## Bot UUID 對照",
        "no_uuid": "- 沒有提供 uuid 對照，文字檔內的原始 id 保持不變。",
        "agents_h": "## 封裝內的 Bot",
        "none": "- （無）",
        "profile_h": "## 身份、設定、例行工作",
        "profile_body": "只有在該 Bot 目錄（或其中的 automations 目錄）已經存在時，才寫入 {sidecars} 個 `.incoming` 附檔。完整副本在 `{kit}`。請先閱讀，再自行把附檔改名成正式檔名。",
        "memory_h": "## 記憶",
        "memory_body": "Level_6 是 `{root}` 的 memory-drop JSONL，以及本機 memory 檔。把檔案放到磁碟上不會重建 RecallMemory。請在目標 Bot 上用它自己的記憶工具匯入每條 `fact`。空的 JSONL 不能證明匯出做過；只有該 Bot 確實查過且沒有記憶時，`memory-status.json` 才有意義。",
        "conv_h": "## 對話（唯讀）",
        "conv_body": "搜尋索引快照與逐字稿只是此資料夾裡的參考副本。訊息正文留在快照資料庫，沒有寫回 live 索引。文字逐字稿裡的 id 與路徑可能已改寫；資料庫檔本身沒有改寫。",
        "content_h": "## 筆記、參考資料、附件、private、專案",
        "content_body": "這些檔案在 `{kit}` 的對應層級目錄。若有 uuid 對照，資料夾名稱已換成目標 id。請自行挑需要的檔案複製到對應的 Bot 目錄。",
        "secrets_h": "## 未打包的機密",
        "heavy_h": "## 只計數、未打包的大檔（Level_5）",
        "stores_h": "## Pages / canvas stores（實驗性）",
        "stores_body": "只列出名稱。此工具沒有在 live Pages 主機上驗證過這個目錄，還原也不會寫入 stores。",
        "skills_gap_h": "## 封裝刻意不含的技能",
        "skills_gap_body": "`managed-skills/` 與 `plugin-skills/` 屬於主機環境，沒有打包。目標機器若需要，請另外安裝。除非封裝時加了 `--include-subagents`，否則不含 sand-subagent 逐字稿。",
        "footer": "若有建立回滾快照，它會在工作區的 `.grok-pre-restore-snapshot_*` 目錄，`ROLLBACK.txt` 列出每個已保存的檔案。",
    },
    "ja": {
        "title": "# Grok Bot 手動再構築チェックリスト ({tracking})",
        "intro": "この復元が直接書いたのはワークスペースのファイルとユーザースキルだけです。プロフィール、設定、ルーチン、メモリ、会話は稼働中のプラットフォームファイルを上書きしていません。",
        "auto_h": "## 自動で書き込んだもの",
        "auto": "- ワークスペース（{workspace_n}）-> `{workspace}`\n- ユーザースキル（{workflow_n}）-> `{workflows}`{skills_note}",
        "skills_held": "\n- agent-data が無いため、スキルは workflows/ ではなくこのフォルダに残しています。",
        "not_h": "## 意図的に書き込んでいないもの",
        "not_body": "- `search-index-snapshot.db` で稼働中の `search-index.db` を置き換えないでください。\n- 稼働中の `agent-transcripts/` を置き換えないでください。\n- 内容を確認する前に `.incoming` を `profile.json` や `settings.json`、ルーチンへ上書きしないでください。\n- `/cursor/stores` へは何もコピーしないでください。",
        "uuid_h": "## Bot UUID の対応",
        "no_uuid": "- UUID 対応表はありません。テキスト内の元の id はそのままです。",
        "agents_h": "## パッケージ内の Bot",
        "none": "- （なし）",
        "profile_h": "## プロフィール、設定、ルーチン",
        "profile_body": "対象 Bot のディレクトリ（ルーチンは automations ディレクトリ）が既にある場合だけ、`.incoming` を {sidecars} 件書きました。完全なコピーは `{kit}` にあります。読んだうえで、採用するファイルだけ自分で正式な名前に変えてください。",
        "memory_h": "## メモリ",
        "memory_body": "Level_6 は `{root}` の memory-drop JSONL と、ローカルの memory ファイルです。ファイルを置いただけでは RecallMemory は再作成されません。各 `fact` は移行先 Bot 自身のメモリ機能で取り込んでください。空の JSONL はエクスポート済みの証明ではありません。`memory-status.json` は、その Bot が実際に確認して記憶が無かったときだけ意味を持ちます。",
        "conv_h": "## 会話（読み取り専用）",
        "conv_body": "検索インデックスのスナップショットとトランスクリプトは、このフォルダの参照用コピーです。本文はスナップショット DB に残っており、稼働中のインデックスへは戻していません。テキスト側の id とパスは書き換えられることがあります。データベースファイル自体は書き換えていません。",
        "content_h": "## ノート、参考資料、添付、private、プロジェクト",
        "content_body": "`{kit}` の各レベルディレクトリにあります。UUID 対応表がある場合、フォルダ名は移行先の id です。必要なものだけ、対応する Bot ディレクトリへ自分でコピーしてください。",
        "secrets_h": "## パッケージに入れなかった機密",
        "heavy_h": "## 件数のみで梱包していない大容量ファイル（Level_5）",
        "stores_h": "## Pages / canvas stores（実験的）",
        "stores_body": "一覧のみです。live の Pages ホストでは未検証で、復元時に stores ディレクトリへは書き込みません。",
        "skills_gap_h": "## パッケージに含まれないスキル",
        "skills_gap_body": "`managed-skills/` と `plugin-skills/` はホスト提供のため梱包していません。必要なら移行先で入れ直してください。`--include-subagents` を付けて作ったパッケージ以外に sand-subagent のトランスクリプトは含まれません。",
        "footer": "ロールバック用スナップショットを作った場合、ワークスペースの `.grok-pre-restore-snapshot_*` にあり、`ROLLBACK.txt` が保存したファイルを列挙します。",
    },
}
