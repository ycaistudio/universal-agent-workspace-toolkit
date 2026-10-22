"""
Universal AI Agent Workspace Toolkit - Packaging Engine (toolkit_pack.py)
Implements Level_X Aligned Staging, Zip Compression, and Manifest Building.
"""

import os
import sys
import json
import shutil
import zipfile
import platform
from datetime import datetime
from pathlib import Path
from toolkit_scanner import win_p, calculate_md5

def run_pack(assets, output_base, user_home, include_level5=False, lang="en"):
    """Executes the export & snapshot backup packaging workflow."""
    now = datetime.now()
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    tracking_id = f"PKG-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"

    packages_dir = output_base / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_base / f"_staging_{ts_str}"
    if staging_dir.exists():
        shutil.rmtree(win_p(staging_dir), ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    file_manifest = {}
    level_counts = {
        "Level_1_Agent_Directives": 0,
        "Level_2_System_Settings": 0,
        "Level_3_Modular_Skills": 0,
        "Level_4_Workspace_Docs": 0,
        "Level_5_Heavy_References": 0
    }

    # 1. Level_1_Agent_Directives
    dst_l1 = staging_dir / "Level_1_Agent_Directives"
    dst_l1.mkdir(parents=True, exist_ok=True)
    ws_base = assets["ws_scan"]
    for fp in assets["Level_1_Agent_Directives"]:
        if fp.exists():
            dst_f = dst_l1 / fp.name
            shutil.copy2(win_p(fp), win_p(dst_f))
            rel_p = str(dst_f.relative_to(staging_dir)).replace("\\", "/")
            file_manifest[rel_p] = {"size": dst_f.stat().st_size, "md5": calculate_md5(dst_f), "level": 1}
            level_counts["Level_1_Agent_Directives"] += 1

    # 2. Level_2_System_Settings (MCP + IDE settings)
    dst_l2 = staging_dir / "Level_2_System_Settings"
    dst_l2.mkdir(parents=True, exist_ok=True)
    mcp_dir = user_home / ".gemini" / "antigravity" / "mcp"
    for fp in assets["Level_2_System_Settings"]:
        if fp.exists() and mcp_dir and mcp_dir.exists():
            try:
                rel_f = fp.relative_to(mcp_dir)
                target_f = dst_l2 / "mcp" / rel_f
                target_f.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(win_p(fp), win_p(target_f))
                rel_p = str(target_f.relative_to(staging_dir)).replace("\\", "/")
                file_manifest[rel_p] = {"size": target_f.stat().st_size, "md5": calculate_md5(target_f), "level": 2}
                level_counts["Level_2_System_Settings"] += 1
            except Exception:
                pass

    # Inject IDE settings into Level_2
    ide_settings = {
        "security.promptForLocalFileProtocolHandling": False,
        "security.workspace.trust.untrustedFiles": "open"
    }
    ide_json = dst_l2 / "ide_user_settings.json"
    ide_json.write_text(json.dumps(ide_settings, indent=4), encoding="utf-8")
    file_manifest["Level_2_System_Settings/ide_user_settings.json"] = {
        "size": ide_json.stat().st_size, "md5": calculate_md5(ide_json), "level": 2
    }
    level_counts["Level_2_System_Settings"] += 1

    # 3. Level_3_Modular_Skills
    dst_l3 = staging_dir / "Level_3_Modular_Skills"
    dst_l3.mkdir(parents=True, exist_ok=True)
    skills_base = user_home / ".gemini" / "config" / "skills"
    for fp in assets["Level_3_Modular_Skills"]:
        if fp.exists() and skills_base.exists():
            try:
                rel_f = fp.relative_to(skills_base)
                target_f = dst_l3 / rel_f
                target_f.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(win_p(fp), win_p(target_f))
                rel_p = str(target_f.relative_to(staging_dir)).replace("\\", "/")
                file_manifest[rel_p] = {"size": target_f.stat().st_size, "md5": calculate_md5(target_f), "level": 3}
                level_counts["Level_3_Modular_Skills"] += 1
            except Exception:
                pass

    # 4. Level_4_Workspace_Docs
    dst_l4 = staging_dir / "Level_4_Workspace_Docs"
    dst_l4.mkdir(parents=True, exist_ok=True)
    if ws_base:
        for fp in assets["Level_4_Workspace_Docs"]:
            if fp.exists():
                try:
                    rel_f = fp.relative_to(ws_base)
                    target_f = dst_l4 / rel_f
                    target_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(win_p(fp), win_p(target_f))
                    rel_p = str(target_f.relative_to(staging_dir)).replace("\\", "/")
                    file_manifest[rel_p] = {"size": target_f.stat().st_size, "md5": calculate_md5(target_f), "level": 4}
                    level_counts["Level_4_Workspace_Docs"] += 1
                except Exception:
                    pass

    # 5. Level_5_Heavy_References (if selected)
    if include_level5 and ws_base:
        dst_l5 = staging_dir / "Level_5_Heavy_References"
        dst_l5.mkdir(parents=True, exist_ok=True)
        for fp, _ in assets["Level_5_Heavy_References"]:
            if fp.exists():
                try:
                    rel_f = fp.relative_to(ws_base)
                    target_f = dst_l5 / rel_f
                    target_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(win_p(fp), win_p(target_f))
                    rel_p = str(target_f.relative_to(staging_dir)).replace("\\", "/")
                    file_manifest[rel_p] = {"size": target_f.stat().st_size, "md5": calculate_md5(target_f), "level": 5}
                    level_counts["Level_5_Heavy_References"] += 1
                except Exception:
                    pass

    # Build package_manifest.json
    total_size_mb = sum(item["size"] for item in file_manifest.values()) / (1024 * 1024)
    zip_filename = (
        f"Level_1_to_5_Full_Archive_{ts_str}.zip" if include_level5
        else f"Level_1_to_4_Core_Workspace_{ts_str}.zip"
    )
    zip_path = packages_dir / zip_filename

    manifest_doc = {
        "manifest_version": "v2.1.0",
        "tracking_id": tracking_id,
        "created_at": now.isoformat(),
        "sender_system": {
            "machine_fingerprint": platform.node(),
            "os": sys.platform,
            "os_release": platform.release(),
            "user": user_home.name,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "skills_count": len(assets["skills_names"])
        },
        "cargo_levels": {
            k: {"count": v, "protection": "ALIGN_LEVEL_X"} for k, v in level_counts.items()
        },
        "packages": [
            {
                "file_name": zip_filename,
                "part_index": 1,
                "total_parts": 1,
                "size_mb": round(total_size_mb, 2)
            }
        ],
        "file_manifest": file_manifest
    }
    manifest_file = staging_dir / "package_manifest.json"
    manifest_file.write_text(json.dumps(manifest_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compress into zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(staging_dir):
            for f in files:
                fp = Path(root) / f
                arc_name = fp.relative_to(staging_dir)
                zipf.write(win_p(fp), arcname=str(arc_name))

    # Self-check verification
    with zipfile.ZipFile(zip_path, "r") as zipf:
        zip_names = set(zipf.namelist())
        for rel_p in file_manifest:
            if rel_p not in zip_names:
                raise RuntimeError(f"Integrity check failed: missing {rel_p} in zip!")

    # Export manifest & toolkit scripts next to packages/ for portability
    shutil.copy2(win_p(manifest_file), win_p(output_base / "package_manifest.json"))
    shutil.rmtree(win_p(staging_dir), ignore_errors=True)

    return {
        "zip_path": zip_path,
        "tracking_id": tracking_id,
        "total_files": len(file_manifest),
        "total_size_mb": round(total_size_mb, 2),
        "level_counts": level_counts
    }
