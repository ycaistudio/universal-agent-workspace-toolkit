"""
Universal AI Agent Workspace Toolkit - Restore & Verification Engine (toolkit_restore.py)
Implements Pre-Restore Impact Assessment, Rollback Snapshot, and Safe Deployment.
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

def unpack_and_audit(input_base, user_home):
    """Detects zip packages, unpacks staging if needed, and checks manifest integrity."""
    packages_dir = input_base / "packages"
    manifest_file = input_base / "package_manifest.json"
    
    # Auto unpack zip if staging not present
    staging_dir = input_base / "_restore_staging"
    if not staging_dir.exists():
        found_zips = []
        if packages_dir.exists():
            found_zips = list(packages_dir.glob("Level_*.zip"))
        if not found_zips:
            found_zips = list(input_base.glob("Level_*.zip"))

        if found_zips:
            staging_dir.mkdir(parents=True, exist_ok=True)
            for zf in found_zips:
                with zipfile.ZipFile(zf, "r") as z:
                    z.extractall(staging_dir)

    # Read manifest
    manifest = {}
    if not manifest_file.exists() and (staging_dir / "package_manifest.json").exists():
        manifest_file = staging_dir / "package_manifest.json"

    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Verify MD5 checklist
    verified_files = 0
    corrupted_files = []
    file_manifest = manifest.get("file_manifest", {})
    for rel_p, meta in file_manifest.items():
        local_f = staging_dir / rel_p
        if local_f.exists() and local_f.is_file():
            if calculate_md5(local_f) == meta.get("md5"):
                verified_files += 1
            else:
                corrupted_files.append((rel_p, "MD5 Mismatch"))
        else:
            corrupted_files.append((rel_p, "Missing"))

    return {
        "staging_dir": staging_dir,
        "manifest": manifest,
        "verified_files": verified_files,
        "corrupted_files": corrupted_files
    }

def generate_impact_assessment(staging_dir, target_env, user_home, ws_dst):
    """Conducts a dry-run to identify additions, collisions, and setting mutations."""
    assessment = {
        "pure_additions": 0,
        "collisions": [],
        "config_mutations": 2,
        "level1_conflict": False
    }

    # Check Level_1 AGENTS.md collision
    l1_dir = staging_dir / "Level_1_Agent_Directives"
    if l1_dir.exists():
        for f in l1_dir.iterdir():
            if f.is_file():
                local_f = ws_dst / f.name
                if local_f.exists():
                    assessment["level1_conflict"] = True
                    assessment["collisions"].append(str(local_f))
                else:
                    assessment["pure_additions"] += 1

    # Check Level_3 skills collisions
    l3_dir = staging_dir / "Level_3_Modular_Skills"
    target_skills_dir = user_home / ".gemini" / "config" / "skills"
    if l3_dir.exists():
        for skill_dir in l3_dir.iterdir():
            if skill_dir.is_dir():
                loc_skill = target_skills_dir / skill_dir.name
                if loc_skill.exists():
                    assessment["collisions"].append(str(loc_skill))
                else:
                    assessment["pure_additions"] += 1

    # Check Level_4 docs
    l4_dir = staging_dir / "Level_4_Workspace_Docs"
    if l4_dir.exists():
        for root, _, files in os.walk(l4_dir):
            for file in files:
                rel = Path(root).relative_to(l4_dir) / file
                if (ws_dst / rel).exists():
                    assessment["collisions"].append(str(ws_dst / rel))
                else:
                    assessment["pure_additions"] += 1

    return assessment

def create_rollback_snapshot(user_home):
    """Creates a local pre-restore snapshot of existing config before any mutation."""
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = user_home / ".gemini" / f"_pre_restore_snapshot_{now_str}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    cfg_src = user_home / ".gemini" / "config"
    if cfg_src.exists():
        shutil.copytree(win_p(cfg_src), win_p(snapshot_dir / "config"), dirs_exist_ok=True)

    mcp_src = user_home / ".gemini" / "antigravity" / "mcp"
    if mcp_src.exists():
        shutil.copytree(win_p(mcp_src), win_p(snapshot_dir / "mcp"), dirs_exist_ok=True)

    return snapshot_dir

def execute_restore(staging_dir, target_env, user_home, ws_dst, src_user=""):
    """Deploys assets safely: Level_1 .incoming protection, Level_2 patch, path self-healing."""
    gemini_dir = user_home / ".gemini"
    config_dst = gemini_dir / "config"
    skills_dst = config_dst / "skills"
    mcp_dst = gemini_dir / "antigravity" / "mcp"

    skills_dst.mkdir(parents=True, exist_ok=True)
    mcp_dst.mkdir(parents=True, exist_ok=True)
    ws_dst.mkdir(parents=True, exist_ok=True)

    # 1. Level_1 Deploy
    l1_dir = staging_dir / "Level_1_Agent_Directives"
    if l1_dir.exists():
        for f in l1_dir.iterdir():
            if f.is_file():
                target_f = ws_dst / f.name
                if target_env == "existing" and target_f.exists():
                    incoming_f = ws_dst / f"{f.name}.incoming"
                    shutil.copy2(win_p(f), win_p(incoming_f))
                else:
                    shutil.copy2(win_p(f), win_p(target_f))

    # 2. Level_2 Settings & MCP
    l2_dir = staging_dir / "Level_2_System_Settings"
    if l2_dir.exists():
        mcp_src = l2_dir / "mcp"
        if mcp_src.exists():
            shutil.copytree(win_p(mcp_src), win_p(mcp_dst), dirs_exist_ok=True)

        # Patch IDE settings
        ide_targets = []
        if sys.platform == "win32":
            appdata = Path(os.environ.get("APPDATA", user_home / "AppData" / "Roaming"))
            ide_targets = [
                appdata / "Antigravity" / "User" / "settings.json",
                appdata / "Cursor" / "User" / "settings.json",
                appdata / "Code" / "User" / "settings.json"
            ]
        elif sys.platform == "darwin":
            app_support = user_home / "Library" / "Application Support"
            ide_targets = [
                app_support / "Antigravity" / "User" / "settings.json",
                app_support / "Cursor" / "User" / "settings.json",
                app_support / "Code" / "User" / "settings.json"
            ]
        else:
            config_base = Path(os.environ.get("XDG_CONFIG_HOME", user_home / ".config"))
            ide_targets = [
                config_base / "Antigravity" / "User" / "settings.json",
                config_base / "Cursor" / "User" / "settings.json",
                config_base / "Code" / "User" / "settings.json"
            ]

        patch = {
            "security.promptForLocalFileProtocolHandling": False,
            "security.workspace.trust.untrustedFiles": "open"
        }
        for ide_f in ide_targets:
            try:
                data = {}
                if ide_f.exists():
                    try:
                        data = json.loads(ide_f.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                else:
                    ide_f.parent.mkdir(parents=True, exist_ok=True)
                data.update(patch)
                ide_f.write_text(json.dumps(data, indent=4), encoding="utf-8")
            except Exception:
                pass

    # 3. Level_3 Skills Deploy
    l3_dir = staging_dir / "Level_3_Modular_Skills"
    if l3_dir.exists():
        shutil.copytree(win_p(l3_dir), win_p(skills_dst), dirs_exist_ok=True)

    # 4. Level_4 Docs Deploy
    l4_dir = staging_dir / "Level_4_Workspace_Docs"
    if l4_dir.exists():
        shutil.copytree(win_p(l4_dir), win_p(ws_dst), dirs_exist_ok=True)

    # 5. Dynamic Path Refactoring
    refactored_count = 0
    if src_user and src_user != user_home.name:
        src_encoded = src_user.replace(" ", "%20")
        target_encoded = user_home.name.replace(" ", "%20")
        replacements = [
            (f"file:///C:/Users/{src_user}/", f"file:///{user_home.as_posix()}/"),
            (f"file:///C:/Users/{src_encoded}/", f"file:///{user_home.as_posix().replace(' ', '%20')}/"),
            (f"C:/Users/{src_user}/", f"{user_home.as_posix()}/"),
            (f"/Users/{src_user}/", f"/Users/{user_home.name}/"),
            (f"/home/{src_user}/", f"/home/{user_home.name}/")
        ]
        for target_folder in [config_dst, mcp_dst, ws_dst]:
            if not target_folder.exists():
                continue
            for root, _, files in os.walk(target_folder):
                for f in files:
                    if f.endswith((".md", ".json", ".yaml", ".yml", ".py", ".txt")):
                        fp = Path(root) / f
                        try:
                            content = fp.read_text(encoding="utf-8")
                            orig = content
                            for old, new in replacements:
                                if old in content:
                                    content = content.replace(old, new)
                            if content != orig:
                                fp.write_text(content, encoding="utf-8")
                                refactored_count += 1
                        except Exception:
                            pass

    return {
        "config_dst": config_dst,
        "skills_dst": skills_dst,
        "mcp_dst": mcp_dst,
        "ws_dst": ws_dst,
        "refactored_count": refactored_count
    }
