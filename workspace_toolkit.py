"""
Universal AI Agent Workspace Toolkit - Main CLI & Agent Console (workspace_toolkit.py)
Unified Single-Entry Architecture supporting Export, Verified Restore, and Audit.
"""

import os
import sys
import argparse
import platform
import shutil
from pathlib import Path

from toolkit_crypto import EncryptionError, encrypt_packages, encrypted_candidate, resolve_encrypted_input
from toolkit_parts import DEFAULT_PART_MB, PartError, validate_part_mb
from toolkit_i18n import detect_language, get_text
from toolkit_grok import (
    GrokError,
    L1, L2, L3, L4, L5, L6, L7, L8,
    build_restore_plan,
    create_grok_snapshot,
    detect_profile,
    execute_grok_restore,
    grok_paths,
    parse_uuid_map,
    run_grok_pack,
    level_audit_count,
    scan_grok_assets,
    summarize_flags,
    summarize_plan,
)
from toolkit_scanner import scan_all_assets
from toolkit_pack import run_pack
from toolkit_restore import (
    unpack_and_audit,
    cleanup_staging,
    generate_impact_assessment,
    create_rollback_snapshot,
    execute_restore,
    MCP_PREFIX,
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BOX = "┌──────────────────────────────────────────────────────────────────┐"
BOX_END = "└──────────────────────────────────────────────────────────────────┘"


def print_banner(title):
    border = "=" * (len(title) + 6)
    print(f"\n{border}")
    print(f"  🤖 {title}")
    print(f"{border}\n")


def print_section(title):
    print(f"\n{BOX}\n│  🔷 {title:<60}│\n{BOX_END}")


def print_items(header, items, limit=8):
    """items: list of dicts with path/reason, or (path, reason) tuples."""
    print(f"  • {header}")
    for it in items[:limit]:
        path, reason = (it["path"], it["reason"]) if isinstance(it, dict) else it
        print(f"    - {path}  [{reason}]")
    if len(items) > limit:
        print(f"    - ... ({len(items) - limit} more)")


def yes_no(prompt, default_yes):
    ans = input(prompt).strip().lower()
    if not ans:
        return default_yes
    return ans in ("y", "yes", "1")


def obtain_passphrase(args, t):
    password = os.environ.get("UAWT_ENCRYPT_PASSPHRASE")
    if password:
        return password
    if args.yes:
        print(f"  ❌ {t('encrypt_pass_missing')}")
        sys.exit(4)
    import getpass
    password = getpass.getpass(f"  {t('ask_passphrase')}")
    if not password:
        print(f"  ❌ {t('encrypt_pass_missing')}")
        sys.exit(4)
    return password


def encrypt_if_requested(args, t, result):
    """Encrypt every written part in place. Updates result["zip_path"] / result["zip_paths"]."""
    if not args.encrypt:
        return result
    paths = result.get("zip_paths") or [result["zip_path"]]
    try:
        encrypted = encrypt_packages(paths, obtain_passphrase(args, t))
    except EncryptionError as exc:
        print(f"  ❌ {t('encrypt_fail').format(path=paths[0], detail=exc)}")
        sys.exit(4)
    print(f"  • {t('encrypt_ok')}")
    result["zip_paths"] = encrypted
    result["zip_path"] = encrypted[0]
    return result


def remove_temps(temps):
    for temp in temps:
        temp = Path(temp)
        if temp.is_dir():
            shutil.rmtree(temp, ignore_errors=True)
        else:
            temp.unlink(missing_ok=True)


def print_preflight(t, assets, max_part_bytes):
    """Warnings shown before the pack confirmation. None of them block (-y still works)."""
    duplicates = assets.get("duplicates") or []
    if duplicates:
        print(f"  ⚠️ {t('dup_hdr').format(count=len(duplicates))}")
        for group in duplicates[:8]:
            kind = t("dup_identical") if group["kind"] == "identical" else t("dup_diverged")
            print(f"    - {group['file']} [{kind}]")
            for location in group["locations"][:6]:
                print(f"        {location}")
        print(f"  💡 {t('dup_action')}")
    venvs = assets.get("venvs") or []
    if venvs:
        print(f"  • {t('venv_found').format(count=len(venvs))}")
    print(f"  • {t('part_cap').format(mb=max_part_bytes / 1000000)}")


def print_pack_extras(t, result):
    paths = result.get("zip_paths") or [result["zip_path"]]
    if len(paths) > 1:
        print(f"  • {t('parts_written').format(count=len(paths))}")
        for path in paths:
            print(f"    - {Path(path).name}")
        print(f"  💡 {t('parts_keep_together')}")
    long_paths = result.get("long_paths") or {}
    if long_paths.get("over_limit"):
        print(f"  ⚠️ {t('long_path_warn').format(chars=long_paths['max_path_chars'], limit=long_paths['limit'])}")
    locks = result.get("env_locks") or {}
    ok = [entry for entry in locks.get("venvs", []) if entry.get("status") == "ok"]
    failed = [entry for entry in locks.get("venvs", []) if entry.get("status") != "ok"]
    if ok or failed:
        print(f"  • {t('env_lock_done').format(ok=len(ok), failed=len(failed))}")
        for entry in failed[:8]:
            print(f"    - {entry['path']}: {entry.get('error')}")
    if result.get("duplicates"):
        print(f"  ⚠️ {t('dup_hdr').format(count=len(result['duplicates']))} → package_manifest.json \"duplicates\"")


def prepare_input(args, t, in_path):
    """Decrypt the newest .zip.enc when it is newer than any plaintext zip."""
    if encrypted_candidate(in_path) is None:
        return in_path, []
    try:
        return resolve_encrypted_input(in_path, obtain_passphrase(args, t))
    except EncryptionError as exc:
        print(f"  ❌ {exc}")
        sys.exit(4)


def destination_grok_paths(args):
    paths = grok_paths()
    if args.workspace_dir:
        paths["workspace"] = Path(args.workspace_dir).resolve()
        paths["search_index"] = paths["agent_data"] / "search-index.db"
    return paths


def print_grok_audit(t, assets):
    print_section(t("sec_audit"))
    print(f"  {t('audit_hdr')}")
    print("  |:--------|:------------------------------|:--------|:----------|:----------------|")
    rows = (
        ("Level_1", "Profile, avatar, directives", L1, "Incoming sidecar"),
        ("Level_2", "Settings and routines", L2, "Incoming sidecar"),
        ("Level_3", "User workflows (skills)", L3, "Restore workflows"),
        ("Level_4", "Workspace, notes, projects", L4, "Workspace direct"),
        ("Level_5", "Heavy references", L5, "Not packed"),
        ("Level_6", "Memory-drop JSONL", L6, "Incoming only"),
        ("Level_7", "Conversations snapshot", L7, "Read-only"),
        ("Level_8", "Cursor stores experimental", L8, "Opt-in / incoming"),
    )
    for lvl, label, key, strategy in rows:
        size = f"{assets['sizes_mb'][key]:.2f} MB"
        print(f"  | {lvl} | {label:<29} | {level_audit_count(assets, key):<7} | {size:<9} | {strategy:<15} |")
    print("  " + "-" * 66)
    print(f"  • {t('core_size').format(size=assets['t_core_mb'])}")
    packed = sum(assets["sizes_mb"][key] for key in (L1, L2, L3, L4, L6, L7, L8))
    print(f"  • Packed levels 1-4 + 6-8 (estimate): {packed:.2f} MB")
    if packed * 1024 * 1024 > assets.get("max_part_bytes", DEFAULT_PART_MB * 1000000):
        print(f"  ⚠️ {t('split_notice').format(mb=assets.get('max_part_bytes', DEFAULT_PART_MB * 1000000) / 1000000)}")
    memory = assets["memory"]
    print(f"  • Memory drop: {memory.get('drop_root')} ({'present' if memory.get('present') else 'absent'})")
    for agent in memory.get("agents") or []:
        facts = sum(item.get("facts", 0) for item in (agent.get("files") or {}).values())
        state = "exported" if agent.get("files") or agent.get("explicit_empty") else "not exported"
        print(f"    - {agent.get('id')}: {state}, facts {facts}")
    for agent in assets.get("agents") or []:
        print(f"  • {agent.get('name')} ({agent.get('id')}): routines {agent.get('routines', 0)}")
    stores = (assets.get("experimental") or {}).get("cursor_stores") or {}
    names = ", ".join(entry.get("name", "") for entry in stores.get("entries") or []) or "(none)"
    print(f"  • {t('grok_experimental').format(summary=names)}")
    for warning in assets["warnings"]:
        print(f"  ⚠️ {warning}")


def pack_grok(args, t, user_home, include_secrets):
    out_base = Path(args.output_dir).resolve() if args.output_dir else Path("./migration_output").resolve()
    if not args.yes:
        print_section(t("sec_dest"))
        cust_p = input(f"  {t('ask_dest').format(default=str(out_base))}").strip()
        if cust_p:
            out_base = Path(cust_p).resolve()
    paths = destination_grok_paths(args)
    include_subagents = args.include_subagents or os.environ.get("INCLUDE_SUBAGENTS", "0") == "1"
    bulky = os.environ.get("INCLUDE_BULKY_DIRS", "0")
    if bulky not in ("0", "1"):
        print(f"  ❌ INCLUDE_BULKY_DIRS is {bulky!r}; the only accepted settings are 0 and 1")
        sys.exit(2)
    if args.include_bulky:
        bulky = "1"
    try:
        assets = scan_grok_assets(
            paths,
            include_secrets=include_secrets,
            include_cursor_stores=args.include_cursor_stores,
            include_subagents=include_subagents,
            include_bulky=bulky == "1",
            exclude_roots=[out_base],
        )
    except GrokError as exc:
        print(f"  ❌ {exc}")
        sys.exit(2)
    assets["max_part_bytes"] = args.max_part_bytes

    print_section(t("sec_lvl0"))
    if include_secrets:
        print(f"  ⚠️ {t('secrets_included')}")
    else:
        if assets["excluded"]:
            print_items(t("lvl0_found").format(count=len(assets["excluded"])), assets["excluded"])
        print(f"  ⚠️ {t('lvl0_policy')}")
        print(f"  💡 {t('lvl0_action')}")
    if assets["flagged"]:
        print(f"  • {t('flagged_hdr').format(count=len(assets['flagged']))}")
        for row in summarize_flags(assets["flagged"], assets["paths"]):
            print(f"    - {row['folder']}: {row['count']} ({row['reason']})")
    print_grok_audit(t, assets)
    print_preflight(t, assets, args.max_part_bytes)
    if not args.yes and not yes_no(f"\n  {t('confirm_pack')}", default_yes=True):
        print("  Packaging cancelled by user.")
        return
    try:
        result = run_grok_pack(assets, out_base, user_home, encrypted=args.encrypt,
                               max_part_bytes=args.max_part_bytes, env_lock=not args.skip_env_lock)
    except PartError as exc:
        print(f"  ❌ {exc}")
        sys.exit(2)
    encrypt_if_requested(args, t, result)
    print("\n" + "=" * 68)
    print(f"  🎉 {t('pack_success')}")
    print("=" * 68)
    print(f"  • Tracking ID   : {result['tracking_id']}")
    print(f"  • Package File  : {result['zip_path']}")
    print(f"  • Total Size    : {result['total_size_mb']} MB (Files: {result['total_files']})")
    print(f"  • Destination   : {out_base}")
    print(f"  • {t('grok_not_written')}")
    print_pack_extras(t, result)
    if result["redacted"]:
        print_items(t("redacted_hdr").format(count=len(result["redacted"])),
                    [(p, "secret values replaced") for p in result["redacted"]])
    print()


def restore_grok(args, t, user_home, audit):
    manifest = audit["manifest"]
    try:
        uuid_map = parse_uuid_map(args.uuid_map, args.uuid_map_file)
    except (GrokError, OSError, ValueError) as exc:
        print(f"  ❌ {exc}")
        sys.exit(2)
    dest = destination_grok_paths(args)
    target_env = args.target_env
    if not target_env and not args.yes:
        print(f"\n  {t('ask_env_state')}")
        print("  " + "-" * 66)
        print(f"  {t('env_fresh')}")
        print(f"  {t('env_existing')}")
        print("  " + "-" * 66)
        target_env = "fresh" if input(f"  {t('ask_env_choice')}").strip() == "1" else "existing"
    elif not target_env:
        target_env = "existing"
    plan = build_restore_plan(audit["staging_dir"], manifest, dest, target_env, uuid_map)
    impact = summarize_plan(plan)
    print_section(t("impact_hdr"))
    print(f"  • Workspace files to write     : {impact['workspace_writes']}")
    print(f"  • User skills to write         : {impact['workflow_writes']}")
    print(f"  • Directive sidecars           : {impact['directive_writes']}")
    print(f"  • Incoming-kit files           : {impact['incoming_files']}")
    print(f"  • .incoming sidecars           : {impact['sidecars']}")
    print(f"  • Existing paths that collide  : {len(impact['collisions'])}")
    print(f"  • {t('grok_not_written')}")
    if not dest["agent_data"].is_dir():
        print(f"  ⚠️ {t('grok_skills_held')}")
    if not args.yes and not yes_no(f"\n  {t('confirm_p1')}", default_yes=True):
        print("  Restore cancelled at Stage 1.")
        return
    snap = create_grok_snapshot(dest["workspace"], dest["agent_data"], plan["actions"])
    print(f"  {t('snapshot_created').format(path=snap)}" if snap else f"  {t('no_snapshot')}")
    if not args.yes and not yes_no(f"\n  {t('confirm_p2')}", default_yes=True):
        if snap:
            shutil.rmtree(snap, ignore_errors=True)
        print("  Restore cancelled at Stage 2.")
        return
    result = execute_grok_restore(plan, manifest, user_home, dest, uuid_map, lang=args.lang or detect_language()[0])
    print("\n" + "=" * 68)
    print(f"  🎉 {t('restore_success')}")
    print("=" * 68)
    print(f"  [OK] Workspace                : {result['workspace']}")
    print(f"  [OK] User skills              : {result['workflows']}")
    print(f"  [OK] Path / UUID remap        : {result['refactored_count']} files updated")
    print(f"  [OK] {t('grok_checklist').format(path=result['checklist'])}")
    print(f"  • {t('grok_not_written')}")
    if snap:
        print(f"  • {t('snapshot_created').format(path=snap)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Universal AI Agent Workspace Toolkit")
    parser.add_argument("--mode", choices=["pack", "restore", "inspect"], default=None, help="Operation mode")
    parser.add_argument("--lang", choices=["en", "zh-tw", "ja"], default=None, help="UI language")
    parser.add_argument("--target-env", choices=["fresh", "existing"], default=None, help="Target Agent state")
    parser.add_argument("--output-dir", default=None, help="Custom export package directory")
    parser.add_argument("--input-dir", default=None, help="Folder holding the package, or the package .zip itself")
    parser.add_argument("--workspace-dir", default=None, help="Custom workspace directory")
    parser.add_argument("--include-secrets", action="store_true",
                        help="Pack passwords, API keys and private keys too (default: excluded)")
    parser.add_argument("--skip-ide-protocol-patch", action="store_true",
                        help="Legacy option (IDE prompt bypass is now disabled by default)")
    parser.add_argument("--enable-ide-prompt-bypass", action="store_true", default=False,
                        help="Restore: explicit opt-in to disable IDE security prompt for file:/// protocol (SEC-03)")
    parser.add_argument("--profile", choices=["auto", "antigravity", "grok"], default=None,
                        help="Environment profile (default: auto). Grok is selected when agent-data exists.")
    parser.add_argument("--encrypt", action="store_true",
                        help="Encrypt the zip with OpenSSL AES-256-CBC. Passphrase: UAWT_ENCRYPT_PASSPHRASE or a prompt.")
    parser.add_argument("--include-cursor-stores", action="store_true",
                        help="Grok: pack /cursor/stores (experimental; restore still will not write them back)")
    parser.add_argument("--include-subagents", action="store_true",
                        help="Grok: include sand-subagent transcripts")
    parser.add_argument("--uuid-map", action="append", default=[],
                        help="Grok restore: OLD=NEW agent id. Repeat for more than one bot.")
    parser.add_argument("--uuid-map-file", default=None,
                        help="Grok restore: JSON object of old agent id to new agent id")
    parser.add_argument("--max-part-mb", default=str(DEFAULT_PART_MB),
                        help="Pack: largest zip to write, in decimal MB (default 90, max 95). "
                             "Bigger kits are split into standalone _Part_NN_of_MM.zip files.")
    parser.add_argument("--include-bulky", action="store_true",
                        help="Pack model weights (.onnx/.pt/.ckpt/.safetensors/large .bin) and, for Grok, "
                             ".venv-style folders without pyvenv.cfg (same as INCLUDE_BULKY_DIRS=1)")
    parser.add_argument("--skip-env-lock", action="store_true",
                        help="Pack: do not write virtualenv requirement locks (python-envs/)")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive auto confirm")
    args = parser.parse_args()
    try:
        args.max_part_bytes = validate_part_mb(args.max_part_mb)
    except PartError as exc:
        parser.error(str(exc))

    user_home = Path.home()
    lang = args.lang or detect_language()[0]
    t = lambda k: get_text(k, lang)

    print_banner(t("title") + " (v2.3.0)")
    host_info = f"{platform.system()} {platform.release()} | User: {user_home.name} | Python {sys.version_info.major}.{sys.version_info.minor}"
    print(f"  [Host]: {host_info}")
    print(f"  [Language]: {lang.upper()}  (Switch: --lang en | --lang zh-tw | --lang ja)")
    try:
        profile = detect_profile(args.profile)
    except GrokError as exc:
        print(f"  ❌ {exc}")
        sys.exit(2)
    print(f"  [Profile]: {t('profile_line').format(profile=profile)}\n")

    mode = args.mode
    if not mode:
        print(f"  {t('menu_prompt')}")
        print("  " + "-" * 66)
        print(f"  {t('opt_1')}")
        print(f"  {t('opt_2')}")
        print(f"  {t('opt_3')}")
        print("  " + "-" * 66)
        choice = input(f"  {t('ask_choice')}").strip()
        mode = {"1": "pack", "2": "restore", "3": "inspect", "": "pack"}.get(choice, "pack")

    # ------------------ MODE: PACK ------------------
    if mode == "pack":
        include_secrets = args.include_secrets
        if not include_secrets and not args.yes:
            include_secrets = yes_no(f"  {t('ask_include_secrets')}", default_yes=False)

        if profile == "grok":
            pack_grok(args, t, user_home, include_secrets)
            return

        assets = scan_all_assets(user_home, args.workspace_dir, include_secrets,
                                 include_bulky=args.include_bulky)

        # Stage 1: Level_0 secret policy report (the same scan the packer uses)
        print_section(t("sec_lvl0"))
        if include_secrets:
            print(f"  ⚠️ {t('secrets_included')}")
        else:
            if assets["excluded"]:
                print_items(t("lvl0_found").format(count=len(assets["excluded"])), assets["excluded"])
            print(f"  ⚠️ {t('lvl0_policy')}")
            print(f"  💡 {t('lvl0_action')}")
        if assets["flagged"]:
            print_items(t("flagged_hdr").format(count=len(assets["flagged"])), assets["flagged"])

        # Stage 2: Asset hierarchy audit (real counts and sizes)
        print_section(t("sec_audit"))
        print(f"  {t('audit_hdr')}")
        print("  |:--------|:------------------------------|:--------|:----------|:----------------|")
        rows = (
            ("Level_1", "Agent Directives (AGENTS.md)", "Level_1_Agent_Directives", "Immutable / Safe"),
            ("Level_2", "System Settings (IDE/MCP)", "Level_2_System_Settings", "Key Patch Only"),
            ("Level_3", "Modular Skills Library", "Level_3_Modular_Skills", "Modular Inject"),
            ("Level_4", "Workspace Project Docs", "Level_4_Workspace_Docs", "Incremental"),
            ("Level_5", "Heavy References (>10MB)", "Level_5_Heavy_References", "Not packed"),
        )
        for lvl, label, key, strategy in rows:
            size = f"{assets['sizes_mb'][key]:.2f} MB"
            print(f"  | {lvl} | {label:<29} | {len(assets[key]):<7} | {size:<9} | {strategy:<15} |")
        print("  " + "-" * 66)
        print(f"  • {t('core_size').format(size=assets['t_core_mb'])}")
        core_mb = sum(assets["sizes_mb"][k] for k in (
            "Level_1_Agent_Directives", "Level_2_System_Settings", "Level_3_Modular_Skills", "Level_4_Workspace_Docs"))
        if core_mb * 1024 * 1024 > args.max_part_bytes:
            print(f"  ⚠️ {t('split_notice').format(mb=args.max_part_bytes / 1000000)}")
        print_preflight(t, assets, args.max_part_bytes)
        print()

        # Stage 3: Destination
        out_base = Path(args.output_dir).resolve() if args.output_dir else Path("./migration_output").resolve()
        if not args.yes:
            print_section(t("sec_dest"))
            cust_p = input(f"  {t('ask_dest').format(default=str(out_base))}").strip()
            if cust_p:
                out_base = Path(cust_p).resolve()
            if not yes_no(f"\n  {t('confirm_pack')}", default_yes=True):
                print("  Packaging cancelled by user.")
                return

        try:
            result = run_pack(assets, out_base, user_home, encrypted=args.encrypt,
                              max_part_bytes=args.max_part_bytes, env_lock=not args.skip_env_lock)
        except PartError as exc:
            print(f"  ❌ {exc}")
            sys.exit(2)
        encrypt_if_requested(args, t, result)
        print("\n" + "=" * 68)
        print(f"  🎉 {t('pack_success')}")
        print("=" * 68)
        print(f"  • Tracking ID   : {result['tracking_id']}")
        print(f"  • Package File  : {result['zip_path']}")
        print(f"  • Total Size    : {result['total_size_mb']} MB (Files: {result['total_files']})")
        print(f"  • Destination   : {out_base}")
        print_pack_extras(t, result)
        if result["redacted"]:
            print_items(t("redacted_hdr").format(count=len(result["redacted"])),
                        [(p, "secret values replaced") for p in result["redacted"]])
        print()

    # ------------------ MODE: RESTORE ------------------
    elif mode == "restore":
        in_path = Path(args.input_dir).resolve() if args.input_dir else Path("./migration_output").resolve()
        if not in_path.exists():
            in_path = Path(".").resolve()

        audit_input, temps = prepare_input(args, t, in_path)
        audit = unpack_and_audit(audit_input)
        try:
            if audit["error"]:
                print(f"  ❌ {audit['error']}")
                sys.exit(2)
            print_section(t("restore_sec1"))
            print(f"  • {t('pkg_chosen').format(name=audit['package'].name)}")
            if len(audit.get("parts") or []) > 1:
                print(f"  • {t('parts_verified').format(count=len(audit['parts']))}")
            for p, why in audit["ignored"]:
                print(f"  • {t('pkg_ignored').format(name=p.name, why=why)}")
            if audit["corrupted_files"]:
                print(f"  ❌ {t('err_corrupt').format(count=len(audit['corrupted_files']))}")
                for rel, why in audit["corrupted_files"][:8]:
                    print(f"    - {rel} [{why}]")
                sys.exit(3)

            manifest = audit["manifest"]
            if manifest.get("profile") == "grok":
                print(f"  • Verified Assets: {audit['verified_files']} items [SHA-256 checked]")
                if manifest.get("excluded"):
                    print_items(t("lvl0_found").format(count=len(manifest["excluded"])), manifest["excluded"])
                restore_grok(args, t, user_home, audit)
                return
            sender = manifest.get("sender_system", {})
            src_user = sender.get("user", "")
            src_host = sender.get("machine_fingerprint", "")
            if src_host == platform.node() and src_user == user_home.name:
                print(f"  • {t('same_machine')}")
            else:
                print(f"  • {t('cross_machine')}")
                print(f"    Source: {src_user} ({sender.get('os')}) ──> Target: {user_home.name} ({sys.platform})")
            print(f"  • Verified Assets: {audit['verified_files']} items [SHA-256 checked]")
            if manifest.get("excluded"):
                print_items(t("lvl0_found").format(count=len(manifest["excluded"])), manifest["excluded"])

            target_env = args.target_env
            if not target_env and not args.yes:
                print(f"\n  {t('ask_env_state')}")
                print("  " + "-" * 66)
                print(f"  {t('env_fresh')}")
                print(f"  {t('env_existing')}")
                print("  " + "-" * 66)
                target_env = "fresh" if input(f"  {t('ask_env_choice')}").strip() == "1" else "existing"
            elif not target_env:
                target_env = "existing"

            apply_ide = bool(args.enable_ide_prompt_bypass)
            ws_dst = Path(args.workspace_dir).resolve() if args.workspace_dir else (user_home / "Documents" / "AI_Workspace").resolve()
            staging = audit["staging_dir"]
            impact = generate_impact_assessment(staging, target_env, user_home, ws_dst, apply_ide)

            print_section(t("impact_hdr"))
            print(f"  • Pure Additions (Safe)     : {impact['pure_additions']} items")
            print(f"  • Setting Mutations (Patch) : {impact['config_mutations']} items")
            print(f"  • Collisions / Existing     : {len(impact['collisions'])} items")
            if impact["level1_conflict"]:
                print("  ⚠️ Level_1 AGENTS.md collision detected on target workspace!")
                if target_env == "existing":
                    print("     🛡️ Local AGENTS.md is kept. The incoming copy is saved as AGENTS.md.incoming.")
                else:
                    print("     ⚠️ FRESH OVERWRITE: Incoming AGENTS.md will initialize workspace.")

            if not args.yes and not yes_no(f"\n  {t('confirm_p1')}", default_yes=True):
                print("  Restore cancelled at Stage 1.")
                return

            # Safety net: always snapshot what the restore could overwrite, with or without -y
            snap = create_rollback_snapshot(user_home, staging, target_env, ws_dst, apply_ide)
            print(f"  {t('snapshot_created').format(path=snap)}" if snap else f"  {t('no_snapshot')}")

            if not args.yes and not yes_no(f"\n  {t('confirm_p2')}", default_yes=True):
                if snap:
                    shutil.rmtree(snap, ignore_errors=True)
                print("  Restore cancelled at Stage 2.")
                return

            res = execute_restore(staging, target_env, user_home, ws_dst, src_user=src_user, apply_ide=apply_ide, rollback_snapshot=snap)
            print("\n" + "=" * 68)
            print(f"  🎉 {t('restore_success')}")
            print("=" * 68)
            print(f"  [OK] Config & Skills Restored : {res['skills_dst']}")
            print(f"  [OK] MCP Definitions          : {res['mcp_dst']}")
            print(f"  [OK] Workspace Documents      : {res['ws_dst']}")
            print(f"  [OK] Path Self-Healing        : {res['refactored_count']} files updated")

            for r in res["ide_report"]:
                if r["status"] == "manual":
                    print(f"  ⚠️ {t('ide_manual').format(path=r['path'])}")
                elif r["status"] in ("patched", "created"):
                    print(f"  [OK] IDE prompt bypass ({r['ide']}): {r['status']}" +
                          (f", backup: {r['backup']}" if r.get("backup") else ""))
            if res["incoming"]:
                print_items(t("incoming_hdr"), [(str(p), "kept local file") for p in res["incoming"]])
            needs_secrets = [(str(res["mcp_dst"] / p[len(MCP_PREFIX):]), "re-enter secret values")
                             for p in manifest.get("redacted", []) if p.startswith(MCP_PREFIX)]
            if needs_secrets:
                print_items(t("redacted_hdr").format(count=len(needs_secrets)), needs_secrets)
            print()
        finally:
            cleanup_staging(audit["staging_dir"])
            remove_temps(temps)

    # ------------------ MODE: INSPECT ------------------
    elif mode == "inspect":
        in_path = Path(args.input_dir).resolve() if args.input_dir else Path("./migration_output").resolve()
        audit_input, temps = prepare_input(args, t, in_path)
        audit = unpack_and_audit(audit_input)
        try:
            if audit["error"]:
                print(f"  ❌ {audit['error']}")
                sys.exit(2)
            print(f"\n  [Package]: {audit['package'].name}")
            if len(audit.get("parts") or []) > 1:
                print(f"  [Parts]: {len(audit['parts'])} ({', '.join(p.name for p in audit['parts'])})")
            print(f"  [Profile]: {audit['manifest'].get('profile', 'antigravity')}")
            print(f"  [Audit Summary]: Verified {audit['verified_files']} files (SHA-256).")
            if audit["manifest"].get("profile") == "grok":
                conversations = audit["manifest"].get("conversations") or {}
                print(f"  [Conversations]: read-only snapshot={conversations.get('snapshot')}")
                memory = audit["manifest"].get("memory_drop") or {}
                print(f"  [Memory drop]: {memory.get('drop_root')} present={memory.get('present')}")
                stores = ((audit["manifest"].get("experimental") or {}).get("cursor_stores") or {})
                names = ", ".join(entry.get("name", "") for entry in stores.get("entries") or []) or "(none)"
                print(f"  [Cursor stores]: {t('grok_experimental').format(summary=names)}")
            if audit["corrupted_files"]:
                print(f"  ❌ Discrepancies: {len(audit['corrupted_files'])} items failed verification.")
                sys.exit(3)
            print("  ✓ Package integrity verified.")
        finally:
            cleanup_staging(audit["staging_dir"])
            remove_temps(temps)


if __name__ == "__main__":
    main()
