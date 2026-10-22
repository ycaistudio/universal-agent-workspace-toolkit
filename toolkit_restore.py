"""
Universal AI Agent Workspace Toolkit - Restore & Verification Engine (toolkit_restore.py)
Implements Pre-Restore Impact Assessment, Rollback Snapshot, and Safe Deployment.

Every restore extracts into a fresh temporary directory, so a previous run can never leak
into the next one. Only the newest package is used; packages are never merged.
"""

import os
import sys
import json
import shutil
import zipfile
import tempfile
from datetime import datetime
from pathlib import Path
from toolkit_scanner import win_p, calculate_sha256

IDE_PATCH = {"security.promptForLocalFileProtocolHandling": False}
MCP_PREFIX = "Level_2_System_Settings/mcp/"


def _read_manifest(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return json.loads(z.read("package_manifest.json").decode("utf-8"))


def find_packages(input_path):
    """A .zip file itself, or the Level_*.zip files in <dir>/packages and <dir>."""
    p = Path(input_path)
    if p.is_file() and p.suffix.lower() == ".zip":
        return [p]
    found = []
    for base in (p / "packages", p):
        if base.is_dir():
            found.extend(base.glob("Level_*.zip"))
    return sorted(set(found))


def unpack_and_audit(input_path):
    """Pick the newest package, extract it to a fresh temp dir, verify SHA-256 for every file.

    The caller owns the returned staging_dir and must delete it (see cleanup_staging).
    """
    candidates, ignored = [], []
    for zp in find_packages(input_path):
        try:
            m = _read_manifest(zp)
            candidates.append((m.get("created_at", ""), zp.stat().st_mtime, zp, m))
        except Exception as e:
            ignored.append((zp, f"unreadable package ({type(e).__name__})"))

    result = {"staging_dir": None, "manifest": {}, "package": None, "ignored": ignored,
              "verified_files": 0, "corrupted_files": [], "error": None}
    if not candidates:
        result["error"] = f"No valid package (Level_*.zip) found in {input_path}"
        return result

    candidates.sort(key=lambda c: (c[0], c[1]))
    _, _, chosen, manifest = candidates[-1]
    ignored.extend((c[2], "older package, not used") for c in candidates[:-1])

    staging = Path(tempfile.mkdtemp(prefix="uawt_restore_"))
    result.update(staging_dir=staging, manifest=manifest, package=chosen)
    with zipfile.ZipFile(chosen) as z:
        z.extractall(staging)

    for rel_p, meta in manifest.get("file_manifest", {}).items():
        local_f = staging / rel_p
        if not local_f.is_file():
            result["corrupted_files"].append((rel_p, "Missing"))
        elif calculate_sha256(local_f) == meta.get("sha256"):
            result["verified_files"] += 1
        else:
            result["corrupted_files"].append((rel_p, "SHA-256 mismatch"))
    return result


def cleanup_staging(staging_dir):
    if staging_dir:
        shutil.rmtree(win_p(staging_dir), ignore_errors=True)


# ---------------------------------------------------------------- IDE settings
def ide_settings_paths(user_home):
    """settings.json locations for IDEs that have been run on this machine (their User dir exists)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", user_home / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = user_home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", user_home / ".config"))
    paths = [(name, base / name / "User" / "settings.json") for name in ("Antigravity", "Cursor", "Code")]
    return [(n, p) for n, p in paths if p.parent.is_dir()]


def apply_ide_patch(user_home):
    """Add the file:/// prompt bypass. Never overwrites a file it cannot parse (VS Code settings may be JSONC)."""
    results = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for name, sp in ide_settings_paths(user_home):
        if not sp.exists():
            sp.write_text(json.dumps(IDE_PATCH, indent=4), encoding="utf-8")
            results.append({"ide": name, "path": sp, "status": "created"})
            continue
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except ValueError:
            results.append({"ide": name, "path": sp, "status": "manual"})
            continue
        if all(data.get(k) == v for k, v in IDE_PATCH.items()):
            results.append({"ide": name, "path": sp, "status": "already"})
            continue
        backup = sp.with_name(f"settings.json.bak-{stamp}")
        shutil.copy2(win_p(sp), win_p(backup))
        data.update(IDE_PATCH)
        sp.write_text(json.dumps(data, indent=4), encoding="utf-8")
        results.append({"ide": name, "path": sp, "status": "patched", "backup": backup})
    return results


# ---------------------------------------------------------------- impact + snapshot
def _staged_files(staging_dir, folder):
    base = staging_dir / folder
    if not base.exists():
        return []
    return [(Path(r) / f, (Path(r) / f).relative_to(base)) for r, _, fs in os.walk(base) for f in fs]


def generate_impact_assessment(staging_dir, target_env, user_home, ws_dst, apply_ide=True):
    """Dry run: what would be added, what collides, what settings would change."""
    mcp_dst = user_home / ".gemini" / "antigravity" / "mcp"
    skills_dst = user_home / ".gemini" / "config" / "skills"
    assessment = {"pure_additions": 0, "collisions": [], "config_mutations": 0, "level1_conflict": False}

    for f, _ in _staged_files(staging_dir, "Level_1_Agent_Directives"):
        if (ws_dst / f.name).exists():
            assessment["level1_conflict"] = True
            assessment["collisions"].append(str(ws_dst / f.name))
        else:
            assessment["pure_additions"] += 1

    for f, rel in _staged_files(staging_dir, "Level_2_System_Settings/mcp"):
        if (mcp_dst / rel).exists():
            assessment["collisions"].append(str(mcp_dst / rel))
            assessment["config_mutations"] += 1
        else:
            assessment["pure_additions"] += 1

    l3_dir = staging_dir / "Level_3_Modular_Skills"
    skill_dirs = [d for d in l3_dir.iterdir() if d.is_dir()] if l3_dir.exists() else []
    for skill_dir in skill_dirs:
        if (skills_dst / skill_dir.name).exists():
            assessment["collisions"].append(str(skills_dst / skill_dir.name))
        else:
            assessment["pure_additions"] += 1

    for _, rel in _staged_files(staging_dir, "Level_4_Workspace_Docs"):
        if (ws_dst / rel).exists():
            assessment["collisions"].append(str(ws_dst / rel))
        else:
            assessment["pure_additions"] += 1

    if apply_ide:
        assessment["config_mutations"] += len(ide_settings_paths(user_home))
    return assessment


def create_rollback_snapshot(user_home, staging_dir, target_env, ws_dst, apply_ide=True):
    """Copy everything the restore could overwrite. Returns the snapshot dir, or None if there was nothing to save."""
    snap = user_home / ".gemini" / f"_pre_restore_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    mapping = []  # (original, copy inside snapshot)

    def save(src, rel):
        dst = snap / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(win_p(src), win_p(dst), dirs_exist_ok=True)
        else:
            shutil.copy2(win_p(src), win_p(dst))
        mapping.append((src, dst))

    for src, rel in ((user_home / ".gemini" / "config", "config"),
                     (user_home / ".gemini" / "antigravity" / "mcp", "mcp")):
        if src.exists():
            save(src, rel)
    if apply_ide:
        for name, sp in ide_settings_paths(user_home):
            if sp.exists():
                save(sp, f"ide/{name}/settings.json")
    for _, rel in _staged_files(staging_dir, "Level_4_Workspace_Docs"):
        if (ws_dst / rel).exists():
            save(ws_dst / rel, f"workspace/{rel.as_posix()}")
    if target_env == "fresh":
        for f, _ in _staged_files(staging_dir, "Level_1_Agent_Directives"):
            if (ws_dst / f.name).exists():
                save(ws_dst / f.name, f"workspace/{f.name}")

    if not mapping:
        return None
    lines = ["Rollback: copy each snapshot item back over its original location.", ""]
    lines += [f"{dst}  ->  {src}" for src, dst in mapping]
    (snap / "ROLLBACK.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return snap


# ---------------------------------------------------------------- deploy
def execute_restore(staging_dir, target_env, user_home, ws_dst, src_user="", apply_ide=True):
    """Deploys assets: Level_1/MCP .incoming protection on existing targets, IDE patch, path self-healing."""
    gemini_dir = user_home / ".gemini"
    config_dst = gemini_dir / "config"
    skills_dst = config_dst / "skills"
    mcp_dst = gemini_dir / "antigravity" / "mcp"

    skills_dst.mkdir(parents=True, exist_ok=True)
    mcp_dst.mkdir(parents=True, exist_ok=True)
    ws_dst.mkdir(parents=True, exist_ok=True)

    incoming = []  # files saved as *.incoming instead of overwriting local ones

    def deploy(src, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target_env == "existing" and target.exists():
            alt = target.with_name(target.name + ".incoming")
            shutil.copy2(win_p(src), win_p(alt))
            incoming.append(alt)
        else:
            shutil.copy2(win_p(src), win_p(target))

    # 1. Level_1 directives
    for f, _ in _staged_files(staging_dir, "Level_1_Agent_Directives"):
        deploy(f, ws_dst / f.name)

    # 2. Level_2 MCP definitions (a redacted copy must never replace a working local config)
    for f, rel in _staged_files(staging_dir, "Level_2_System_Settings/mcp"):
        deploy(f, mcp_dst / rel)
    ide_report = apply_ide_patch(user_home) if apply_ide else []

    # 3. Level_3 skills, 4. Level_4 docs
    l3_dir = staging_dir / "Level_3_Modular_Skills"
    if l3_dir.exists():
        shutil.copytree(win_p(l3_dir), win_p(skills_dst), dirs_exist_ok=True)
    l4_dir = staging_dir / "Level_4_Workspace_Docs"
    if l4_dir.exists():
        shutil.copytree(win_p(l4_dir), win_p(ws_dst), dirs_exist_ok=True)

    # 5. Dynamic path refactoring (source username -> target username)
    refactored_count = 0
    if src_user and src_user != user_home.name:
        replacements = [
            (f"file:///C:/Users/{src_user}/", f"file:///{user_home.as_posix()}/"),
            (f"file:///C:/Users/{src_user.replace(' ', '%20')}/", f"file:///{user_home.as_posix().replace(' ', '%20')}/"),
            (f"C:/Users/{src_user}/", f"{user_home.as_posix()}/"),
            (f"/Users/{src_user}/", f"/Users/{user_home.name}/"),
            (f"/home/{src_user}/", f"/home/{user_home.name}/"),
        ]
        for target_folder in (config_dst, mcp_dst, ws_dst):
            if not target_folder.exists():
                continue
            for root, _, files in os.walk(target_folder):
                for f in files:
                    if f.endswith((".md", ".json", ".yaml", ".yml", ".py", ".txt")):
                        fp = Path(root) / f
                        try:
                            content = fp.read_text(encoding="utf-8")
                            new = content
                            for old, rep in replacements:
                                new = new.replace(old, rep)
                            if new != content:
                                fp.write_text(new, encoding="utf-8")
                                refactored_count += 1
                        except Exception:
                            pass

    return {
        "config_dst": config_dst,
        "skills_dst": skills_dst,
        "mcp_dst": mcp_dst,
        "ws_dst": ws_dst,
        "refactored_count": refactored_count,
        "ide_report": ide_report,
        "incoming": incoming,
    }
