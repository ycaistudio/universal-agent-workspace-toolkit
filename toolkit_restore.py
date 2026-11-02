"""
Universal AI Agent Workspace Toolkit - Restore & Verification Engine (toolkit_restore.py)
Implements Pre-Restore Impact Assessment, Rollback Snapshot, and Safe Deployment.

Every restore extracts into a fresh temporary directory, so a previous run can never leak
into the next one. Only the newest package is used; packages are never merged.
The parts of one split package are a single package.
"""

import os
import sys
import re
import json
import shutil
import zipfile
import tempfile
import re
from datetime import datetime
from pathlib import Path
from toolkit_scanner import win_p, calculate_sha256
from toolkit_parts import join_chunks, sibling_parts

IDE_PATCH = {"security.promptForLocalFileProtocolHandling": False}
MCP_PREFIX = "Level_2_System_Settings/mcp/"

MAX_ZIP_ENTRIES = 10000
MAX_ZIP_SINGLE_FILE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_ZIP_COMPRESSION_RATIO = 100.0


class ZipSecurityError(RuntimeError):
    pass


def safe_extract_zip(zip_path, staging_dir, max_files=MAX_ZIP_ENTRIES,
                     max_single_size=MAX_ZIP_SINGLE_FILE_BYTES,
                     max_total_size=MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
                     max_ratio=MAX_ZIP_COMPRESSION_RATIO):
    """Safely inspect central directory and extract ZIP members with resource exhaustion guards (SEC-05)."""
    staging_dir = Path(staging_dir)
    staging_resolved = staging_dir.resolve()
    with zipfile.ZipFile(zip_path) as z:
        infolist = z.infolist()
        if len(infolist) > max_files:
            raise ZipSecurityError(f"ZIP bomb protection: file count {len(infolist)} exceeds limit {max_files}")
        total_size = 0
        seen_names = set()
        for info in infolist:
            name = info.filename.replace("\\", "/")
            if "\0" in name:
                raise ZipSecurityError(f"Illegal null byte in zip entry: {name}")
            if name.startswith("/") or re.match(r"^[a-zA-Z]:", name):
                raise ZipSecurityError(f"Illegal absolute path in zip entry: {name}")
            parts = name.split("/")
            if ".." in parts:
                raise ZipSecurityError(f"Path traversal detected in zip entry: {name}")
            if name in seen_names:
                raise ZipSecurityError(f"Duplicate entry in zip archive: {name}")
            seen_names.add(name)
            if info.file_size > max_single_size:
                raise ZipSecurityError(f"File {name} uncompressed size {info.file_size} exceeds single limit {max_single_size}")
            total_size += info.file_size
            if total_size > max_total_size:
                raise ZipSecurityError(f"Total uncompressed size {total_size} exceeds total limit {max_total_size}")
            if info.file_size > 10240:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > max_ratio:
                    raise ZipSecurityError(f"ZIP bomb protection: file {name} compression ratio {ratio:.1f} exceeds {max_ratio}")

        for info in infolist:
            name = info.filename.replace("\\", "/")
            dest = staging_dir
            for p in name.split("/"):
                if p and p != ".":
                    dest = dest / p
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.resolve().relative_to(staging_resolved)
            except ValueError:
                raise ZipSecurityError(f"Entry {name} escapes staging directory")
            with z.open(info) as src_f, open(dest, "wb") as dst_f:
                written = 0
                while chunk := src_f.read(65536):
                    written += len(chunk)
                    if written > max_single_size:
                        raise ZipSecurityError(f"Streamed extraction of {name} exceeded single file size cap")
                    dst_f.write(chunk)


def validate_manifest_schema(manifest):
    """Validate manifest schema, types, and structure (REL-07). Returns (is_valid, errors)."""
    errors = []
    if not isinstance(manifest, dict):
        return False, ["Manifest is not a JSON object"]
    required_keys = ["manifest_version", "profile", "tracking_id", "created_at", "file_manifest"]
    for k in required_keys:
        if k not in manifest:
            errors.append(f"Missing required manifest field: {k}")
    if "file_manifest" in manifest:
        fm = manifest["file_manifest"]
        if not isinstance(fm, dict):
            errors.append("file_manifest must be an object")
        else:
            for path, meta in fm.items():
                if not isinstance(meta, dict):
                    errors.append(f"file_manifest entry '{path}' must be an object")
                elif "sha256" not in meta or "size" not in meta:
                    errors.append(f"file_manifest entry '{path}' missing sha256 or size")
                elif not isinstance(meta.get("sha256"), str) or len(meta["sha256"]) != 64:
                    errors.append(f"file_manifest entry '{path}' has invalid sha256 format")
    return len(errors) == 0, errors


class RestoreTransaction:
    """Manages transactional restore and rollback (REL-03)."""
    def __init__(self, rollback_snapshot_dir=None):
        self.snapshot_dir = Path(rollback_snapshot_dir) if rollback_snapshot_dir else None
        self.created_files = []
        self.modified_files = []
        self.created_dirs = []
        self.committed = False
        self.log = []

    def record_create(self, path):
        self.created_files.append(Path(path))
        self.log.append(f"CREATE: {path}")

    def record_modify(self, path, backup_path):
        self.modified_files.append((Path(path), Path(backup_path)))
        self.log.append(f"MODIFY: {path}")

    def record_dir(self, path):
        self.created_dirs.append(Path(path))

    def rollback(self):
        """Rollback all changes made during the restore transaction."""
        for p in reversed(self.created_files):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink(missing_ok=True)
            except OSError:
                pass
        for orig, backup in self.modified_files:
            try:
                if backup.is_file():
                    shutil.copy2(win_p(backup), win_p(orig))
            except OSError:
                pass
        for d in reversed(self.created_dirs):
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass
        self.log.append("TRANSACTION_ROLLED_BACK")

    def commit(self):
        self.committed = True
        self.log.append("TRANSACTION_COMMITTED")


def _read_manifest(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return json.loads(z.read("package_manifest.json").decode("utf-8"))


def find_packages(input_path):
    """A .zip file itself, or the Level_*.zip files in <dir>/packages and <dir>.

    A single ``*_Part_NN_of_MM.zip`` also brings in the other parts beside it.
    """
    p = Path(input_path)
    if p.is_file() and p.suffix.lower() == ".zip":
        return sibling_parts(p)
    found = []
    for base in (p / "packages", p):
        if base.is_dir():
            found.extend(base.glob("Level_*.zip"))
    return sorted(set(found))


def _verify_into(staging, file_manifest, result, verified):
    for rel_p, meta in file_manifest.items():
        local_f = staging / rel_p
        if not local_f.is_file():
            result["corrupted_files"].append((rel_p, "Missing"))
        elif calculate_sha256(local_f) == meta.get("sha256"):
            verified.add(rel_p)
        else:
            result["corrupted_files"].append((rel_p, "SHA-256 mismatch"))


def unpack_and_audit(input_path):
    """Pick the newest package, extract it to a fresh temp dir, verify SHA-256 for every file.

    A split package (``*_Part_NN_of_MM.zip``) counts as one package. Every part
    must be present; all parts are extracted, verified, and files that were
    split across parts are re-joined and checked against their full SHA-256.
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
              "verified_files": 0, "corrupted_files": [], "error": None, "parts": []}
    if not candidates:
        result["error"] = f"No valid package (Level_*.zip) found in {input_path}"
        return result

    candidates.sort(key=lambda c: (c[0], c[1]))
    _, _, chosen, manifest = candidates[-1]
    split = manifest.get("split")
    if split:
        members = [c for c in candidates if (c[3].get("split") or {}).get("set_id") == split.get("set_id")
                   and (c[3].get("split") or {}).get("parts") == split.get("parts")]
        ignored.extend((c[2], "older package, not used") for c in candidates if c not in members)
        by_part = {}
        for c in members:
            by_part.setdefault(c[3]["split"]["part"], c)
        count = int(split.get("parts", 0))
        missing = [n for n in range(1, count + 1) if n not in by_part]
        if missing:
            names = split.get("part_names") or []
            labels = ", ".join(names[n - 1] if n - 1 < len(names) else str(n) for n in missing)
            result["error"] = (f"Split package {split.get('set_id')} is incomplete: "
                               f"missing part(s) {', '.join(map(str, missing))} of {count} ({labels}). "
                               "Copy every part into the same folder.")
            result["package"] = chosen
            return result
        ordered = [by_part[n] for n in range(1, count + 1)]
        manifest = dict(ordered[0][3])
        staging = Path(tempfile.mkdtemp(prefix="uawt_restore_"))
        result.update(staging_dir=staging, package=ordered[0][2], parts=[c[2] for c in ordered])
        merged = {}
        valid_schema, schema_errs = validate_manifest_schema(manifest)
        if not valid_schema:
            result["error"] = f"Manifest schema validation failed: {'; '.join(schema_errs)}"
            return result
        for c in ordered:
            try:
                safe_extract_zip(c[2], staging)
            except ZipSecurityError as ze:
                result["error"] = str(ze)
                return result
            merged.update(c[3].get("file_manifest", {}))
        verified = set()
        _verify_into(staging, merged, result, verified)
        final, bad = join_chunks(staging, merged, split.get("chunked_files", {}), verified)
        result["corrupted_files"].extend(bad)
        manifest["file_manifest"] = final
        result["manifest"] = manifest
        result["verified_files"] = sum(1 for rel in final if rel in verified or rel in split.get("chunked_files", {}))
        return result

    ignored.extend((c[2], "older package, not used") for c in candidates[:-1])
    staging = Path(tempfile.mkdtemp(prefix="uawt_restore_"))
    result.update(staging_dir=staging, manifest=manifest, package=chosen, parts=[chosen])
    valid_schema, schema_errs = validate_manifest_schema(manifest)
    if not valid_schema:
        result["error"] = f"Manifest schema validation failed: {'; '.join(schema_errs)}"
        return result
    try:
        safe_extract_zip(chosen, staging)
    except ZipSecurityError as ze:
        result["error"] = str(ze)
        return result

    verified = set()
    _verify_into(staging, manifest.get("file_manifest", {}), result, verified)
    result["verified_files"] = len(verified)
    return result


def cleanup_staging(staging_dir):
    if staging_dir:
        shutil.rmtree(win_p(staging_dir), ignore_errors=True)


# ---------------------------------------------------------------- IDE settings

def revert_ide_patch(user_home):
    """Revert the file:/// prompt bypass in settings.json to restore original IDE security defaults (SEC-03)."""
    results = []
    for name, sp in ide_settings_paths(user_home):
        if not sp.exists():
            continue
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            if "security.promptForLocalFileProtocolHandling" in data:
                del data["security.promptForLocalFileProtocolHandling"]
                sp.write_text(json.dumps(data, indent=4), encoding="utf-8")
                results.append({"ide": name, "path": sp, "status": "reverted"})
        except Exception:
            pass
    return results

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


def generate_impact_assessment(staging_dir, target_env, user_home, ws_dst, apply_ide=False):
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


def create_rollback_snapshot(user_home, staging_dir, target_env, ws_dst, apply_ide=False):
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
def execute_restore(staging_dir, target_env, user_home, ws_dst, src_user="", apply_ide=False, rollback_snapshot=None):
    """Deploys assets: Level_1/MCP .incoming protection on existing targets, IDE patch, path self-healing."""
    gemini_dir = user_home / ".gemini"
    config_dst = gemini_dir / "config"
    skills_dst = config_dst / "skills"
    mcp_dst = gemini_dir / "antigravity" / "mcp"

    skills_dst.mkdir(parents=True, exist_ok=True)
    mcp_dst.mkdir(parents=True, exist_ok=True)
    ws_dst.mkdir(parents=True, exist_ok=True)

    incoming = []
    tx = RestoreTransaction(rollback_snapshot)

    def deploy(src, target):
        dest = Path(target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            tx.record_create(dest)
            shutil.copy2(win_p(src), win_p(dest))
        elif target_env == "existing":
            alt = dest.with_name(dest.name + ".incoming")
            tx.record_create(alt)
            shutil.copy2(win_p(src), win_p(alt))
            incoming.append(alt)
        else:
            # fresh: overwriting existing file
            tx.record_modify(dest, dest)
            shutil.copy2(win_p(src), win_p(dest))

    try:
        # 1. Level_1 directives (REL-01: preserve nested relative paths)
        l1_dir = staging_dir / "Level_1_Agent_Directives"
        if l1_dir.exists():
            for f, rel in _staged_files(staging_dir, "Level_1_Agent_Directives"):
                deploy(f, ws_dst / rel)

        # 2. Level_2 MCP definitions
        for f, rel in _staged_files(staging_dir, "Level_2_System_Settings/mcp"):
            deploy(f, mcp_dst / rel)
        ide_report = apply_ide_patch(user_home) if apply_ide else []

        # 3. Level_3 skills
        l3_dir = staging_dir / "Level_3_Modular_Skills"
        if l3_dir.exists():
            for f, rel in _staged_files(staging_dir, "Level_3_Modular_Skills"):
                deploy(f, skills_dst / rel)

        # 4. Level_4 docs
        l4_dir = staging_dir / "Level_4_Workspace_Docs"
        if l4_dir.exists():
            for f, rel in _staged_files(staging_dir, "Level_4_Workspace_Docs"):
                deploy(f, ws_dst / rel)
        tx.commit()
    except Exception as exc:
        tx.rollback()
        raise RuntimeError(f"Restore failed and transaction rolled back: {exc}") from exc

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
