"""
Universal AI Agent Workspace Toolkit - Main CLI & Agent Console (workspace_toolkit.py)
Unified Single-Entry Architecture supporting Export, Verified Restore, and Audit.
"""

import sys
import argparse
import platform
import shutil
from pathlib import Path

from toolkit_i18n import detect_language, get_text
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
                        help="Restore: do not add the IDE file:/// prompt bypass")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive auto confirm")
    args = parser.parse_args()

    user_home = Path.home()
    lang = args.lang or detect_language()[0]
    t = lambda k: get_text(k, lang)

    print_banner(t("title") + " (v2.1.0)")
    host_info = f"{platform.system()} {platform.release()} | User: {user_home.name} | Python {sys.version_info.major}.{sys.version_info.minor}"
    print(f"  [Host]: {host_info}")
    print(f"  [Language]: {lang.upper()}  (Switch: --lang en | --lang zh-tw | --lang ja)\n")

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

        assets = scan_all_assets(user_home, args.workspace_dir, include_secrets)

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
        print(f"  • {t('core_size').format(size=assets['t_core_mb'])}\n")

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

        result = run_pack(assets, out_base, user_home)
        print("\n" + "=" * 68)
        print(f"  🎉 {t('pack_success')}")
        print("=" * 68)
        print(f"  • Tracking ID   : {result['tracking_id']}")
        print(f"  • Package File  : {result['zip_path']}")
        print(f"  • Total Size    : {result['total_size_mb']} MB (Files: {result['total_files']})")
        print(f"  • Destination   : {out_base}")
        if result["redacted"]:
            print_items(t("redacted_hdr").format(count=len(result["redacted"])),
                        [(p, "secret values replaced") for p in result["redacted"]])
        print()

    # ------------------ MODE: RESTORE ------------------
    elif mode == "restore":
        in_path = Path(args.input_dir).resolve() if args.input_dir else Path("./migration_output").resolve()
        if not in_path.exists():
            in_path = Path(".").resolve()

        audit = unpack_and_audit(in_path)
        try:
            if audit["error"]:
                print(f"  ❌ {audit['error']}")
                sys.exit(2)
            print_section(t("restore_sec1"))
            print(f"  • {t('pkg_chosen').format(name=audit['package'].name)}")
            for p, why in audit["ignored"]:
                print(f"  • {t('pkg_ignored').format(name=p.name, why=why)}")
            if audit["corrupted_files"]:
                print(f"  ❌ {t('err_corrupt').format(count=len(audit['corrupted_files']))}")
                for rel, why in audit["corrupted_files"][:8]:
                    print(f"    - {rel} [{why}]")
                sys.exit(3)

            manifest = audit["manifest"]
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

            apply_ide = not args.skip_ide_protocol_patch
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

            res = execute_restore(staging, target_env, user_home, ws_dst, src_user=src_user, apply_ide=apply_ide)
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

    # ------------------ MODE: INSPECT ------------------
    elif mode == "inspect":
        in_path = Path(args.input_dir).resolve() if args.input_dir else Path("./migration_output").resolve()
        audit = unpack_and_audit(in_path)
        try:
            if audit["error"]:
                print(f"  ❌ {audit['error']}")
                sys.exit(2)
            print(f"\n  [Package]: {audit['package'].name}")
            print(f"  [Audit Summary]: Verified {audit['verified_files']} files (SHA-256).")
            if audit["corrupted_files"]:
                print(f"  ❌ Discrepancies: {len(audit['corrupted_files'])} items failed verification.")
                sys.exit(3)
            print("  ✓ Package integrity verified.")
        finally:
            cleanup_staging(audit["staging_dir"])


if __name__ == "__main__":
    main()
