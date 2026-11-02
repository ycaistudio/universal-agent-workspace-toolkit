"""
Universal AI Agent Workspace Toolkit - Packaging Engine (toolkit_pack.py)
Implements Level_X Aligned Staging, Zip Compression, and Manifest Building.

v2.3.0: output is capped per zip (--max-part-mb, default 90, hard max 95 decimal MB);
larger kits are written as standalone parts (see toolkit_parts). Existing files are
never overwritten. Virtualenv requirement locks are added under Level_2/python-envs.

The packer only COPIES from the source machine. It never modifies or deletes originals.
"""

import sys
import shutil
import uuid
import platform
from datetime import datetime
from pathlib import Path
from toolkit_scanner import win_p, calculate_sha256, redact_mcp_json
from toolkit_parts import DEFAULT_PART_BYTES, write_package
from toolkit_preflight import LOCK_DIR, emit_env_locks

LEVELS = (
    "Level_1_Agent_Directives",
    "Level_2_System_Settings",
    "Level_3_Modular_Skills",
    "Level_4_Workspace_Docs",
    "Level_5_Heavy_References",
)


def _record(dst_f, staging_dir, level, file_manifest):
    rel = str(dst_f.relative_to(staging_dir)).replace("\\", "/")
    file_manifest[rel] = {"size": dst_f.stat().st_size, "sha256": calculate_sha256(dst_f), "level": level}
    return rel


def _copy(fp, dst_f, staging_dir, level, file_manifest):
    dst_f.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(win_p(fp), win_p(dst_f))
    return _record(dst_f, staging_dir, level, file_manifest)


def _display(path, user_home):
    try:
        return "~/" + Path(path).resolve().relative_to(user_home.resolve()).as_posix()
    except Exception:
        return str(path)


def _level5_rel(fp, bases):
    for base in bases:
        if base:
            try:
                return Path(fp).relative_to(base)
            except ValueError:
                continue
    return Path(Path(fp).name)


def run_pack(assets, output_base, user_home, include_level5=False, encrypted=False,
             max_part_bytes=DEFAULT_PART_BYTES, env_lock=True):
    """Executes the export & snapshot backup packaging workflow."""
    include_secrets = assets["include_secrets"]
    now = datetime.now()
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    pkg_uuid = uuid.uuid4().hex[:8]
    tracking_id = f"PKG-{now.strftime('%Y%m%d-%H%M%S')}-{pkg_uuid}"

    packages_dir = output_base / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_base / f"_staging_{ts_str}_{pkg_uuid}"
    if staging_dir.exists():
        shutil.rmtree(win_p(staging_dir), ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        file_manifest = {}
        level_counts = {k: 0 for k in LEVELS}
        excluded = [{"path": _display(p, user_home), "reason": r} for p, r in assets["excluded"]]
        flagged = [{"path": _display(p, user_home), "reason": r} for p, r in assets["flagged"]]
        redacted = []

        ws_base = assets["ws_scan"]
        skills_base = user_home / ".gemini" / "config" / "skills"
        mcp_dir = user_home / ".gemini" / "antigravity" / "mcp"

        # Level_1 agent directives (REL-01: preserve nested relative paths)
        for fp in assets["Level_1_Agent_Directives"]:
            try:
                rel_to_ws = fp.relative_to(ws_base)
            except (ValueError, AttributeError):
                rel_to_ws = Path(fp.name)
            _copy(fp, staging_dir / LEVELS[0] / rel_to_ws, staging_dir, 1, file_manifest)
            level_counts[LEVELS[0]] += 1

        # Level_2 MCP definitions: secret values are replaced unless the user opted in
        for fp in assets["Level_2_System_Settings"]:
            target_f = staging_dir / LEVELS[1] / "mcp" / fp.relative_to(mcp_dir)
            if include_secrets:
                _copy(fp, target_f, staging_dir, 2, file_manifest)
            else:
                try:
                    text, replaced = redact_mcp_json(fp.read_text(encoding="utf-8"))
                except ValueError:
                    excluded.append({"path": _display(fp, user_home),
                                     "reason": "MCP JSON could not be parsed, so secrets cannot be redacted safely"})
                    continue
                if replaced:
                    target_f.parent.mkdir(parents=True, exist_ok=True)
                    target_f.write_text(text, encoding="utf-8")
                    redacted.append(_record(target_f, staging_dir, 2, file_manifest))
                else:
                    _copy(fp, target_f, staging_dir, 2, file_manifest)
            level_counts[LEVELS[1]] += 1

        # Level_3 skills
        for fp in assets["Level_3_Modular_Skills"]:
            _copy(fp, staging_dir / LEVELS[2] / fp.relative_to(skills_base), staging_dir, 3, file_manifest)
            level_counts[LEVELS[2]] += 1

        # Level_4 workspace docs
        for fp in assets["Level_4_Workspace_Docs"]:
            _copy(fp, staging_dir / LEVELS[3] / fp.relative_to(ws_base), staging_dir, 4, file_manifest)
            level_counts[LEVELS[3]] += 1

        # Level_5 heavy references (only when explicitly requested)
        if include_level5:
            for fp, _ in assets["Level_5_Heavy_References"]:
                rel = _level5_rel(fp, (ws_base, skills_base))
                _copy(fp, staging_dir / LEVELS[4] / rel, staging_dir, 5, file_manifest)
                level_counts[LEVELS[4]] += 1

        # Virtualenvs are not copied; their requirement locks are (offline freeze).
        env_locks = None
        if env_lock:
            lock_dir = staging_dir / LEVELS[1] / LOCK_DIR
            env_locks = emit_env_locks(assets.get("venvs", []), lock_dir, display=lambda p: _display(p, user_home))
            if lock_dir.is_dir():
                for lock in sorted(lock_dir.iterdir()):
                    _record(lock, staging_dir, 2, file_manifest)

        total_size_mb = sum(item["size"] for item in file_manifest.values()) / (1024 * 1024)
        zip_stem = (
            f"Level_1_to_5_Full_Archive_{ts_str}" if include_level5
            else f"Level_1_to_4_Core_Workspace_{ts_str}"
        )

        manifest_doc = {
            "manifest_version": "v2.3.0",
            "profile": "antigravity",
            "tracking_id": tracking_id,
            "created_at": now.isoformat(),
            "include_secrets": include_secrets,
            "encrypted": encrypted,
            "sender_system": {
                "machine_fingerprint": platform.node(),
                "os": sys.platform,
                "os_release": platform.release(),
                "user": user_home.name,
                "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "skills_count": len(assets["skills_names"])
            },
            "cargo_levels": {k: {"count": v} for k, v in level_counts.items()},
            "excluded": excluded,
            "redacted": redacted,
            "flagged": flagged,
            "skipped_dirs": [{"path": _display(p, user_home), "reason": r} for p, r in assets.get("skipped", [])],
            "env_locks": env_locks,
            "duplicates": assets.get("duplicates", []),
            "file_manifest": file_manifest
        }
        # Writes one zip, or standalone parts when the cap is exceeded; self-checks every entry.
        zip_paths = write_package(staging_dir, manifest_doc, packages_dir, zip_stem, max_part_bytes)
        zip_path = zip_paths[0]
    finally:
        shutil.rmtree(win_p(staging_dir), ignore_errors=True)

    return {
        "zip_path": zip_path,
        "zip_paths": zip_paths,
        "long_paths": manifest_doc.get("long_paths"),
        "env_locks": env_locks,
        "duplicates": manifest_doc["duplicates"],
        "tracking_id": tracking_id,
        "total_files": len(file_manifest),
        "total_size_mb": round(total_size_mb, 2),
        "level_counts": level_counts,
        "excluded": excluded,
        "redacted": redacted,
        "flagged": flagged,
    }
