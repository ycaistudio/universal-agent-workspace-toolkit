"""
Universal AI Agent Workspace Toolkit - Asset & Credential Scanner (toolkit_scanner.py)
Implements Level_0 Sensitive Credential Probing and Level_1 to Level_5 Classification.
"""

import os
import sys
import hashlib
from pathlib import Path

def win_p(p):
    s = str(Path(p).resolve())
    if sys.platform == "win32":
        prefix = "\\\\?\\"
        if not s.startswith(prefix) and not s.startswith("\\\\"):
            return prefix + s
    return s

def calculate_md5(fp):
    h = hashlib.md5()
    try:
        with open(win_p(fp), "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

EXCLUDED_DIRS = {
    ".git", ".svn", ".hg", "node_modules", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".idea", ".vscode",
    "dist", "build", "coverage", ".parcel-cache", ".next", ".turbo",
    "brain", ".system_generated", "logs", "cache", "tmp", "temp"
}

SENSITIVE_PATTERNS = [
    ".env", ".env.local", ".env.production", "credentials", "id_rsa",
    "id_ed25519", "auth.json", "token.json", "private_key.pem", "secrets.json"
]

def scan_level0_credentials(user_home, workspace_dir=None):
    """Scans and detects Level_0 Sensitive Credentials (excluded from packaging)."""
    detected_creds = []
    scan_targets = []
    
    gemini_config = user_home / ".gemini" / "config"
    if gemini_config.exists():
        scan_targets.append(gemini_config)
    gemini_ag = user_home / ".gemini" / "antigravity"
    if gemini_ag.exists():
        scan_targets.append(gemini_ag)
    ssh_dir = user_home / ".ssh"
    if ssh_dir.exists():
        scan_targets.append(ssh_dir)
    if workspace_dir and Path(workspace_dir).exists():
        scan_targets.append(Path(workspace_dir))
        
    for target in scan_targets:
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for f in files:
                f_lower = f.lower()
                for pat in SENSITIVE_PATTERNS:
                    if pat == f_lower or (pat in f_lower and not f_lower.endswith((".py", ".md", ".txt"))):
                        detected_creds.append(Path(root) / f)
                        break
                        
    return list(dict.fromkeys(detected_creds))

def scan_all_assets(user_home, custom_ws=None):
    """Scans system and workspace, classifying into Level_1 through Level_5."""
    assets = {
        "Level_1_Agent_Directives": [],
        "Level_2_System_Settings": [],
        "Level_3_Modular_Skills": [],
        "Level_4_Workspace_Docs": [],
        "Level_5_Heavy_References": [],
        "skills_names": [],
        "ws_scan": None,
        "t_core_mb": 0.0
    }

    # 1. Level_1 Directives & Level_3 Skills
    skills_dir = user_home / ".gemini" / "config" / "skills"
    if skills_dir.exists():
        for d in skills_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                assets["skills_names"].append(d.name)
                for root, dirs, files in os.walk(d):
                    dirs[:] = [sub for sub in dirs if sub not in EXCLUDED_DIRS]
                    for f in files:
                        fp = Path(root) / f
                        if not any(k in f.lower() for k in [".env", "secret", "token", "credential"]):
                            assets["Level_3_Modular_Skills"].append(fp)

    # Level_2 MCP
    mcp_dir = user_home / ".gemini" / "antigravity" / "mcp"
    if mcp_dir.exists():
        for root, dirs, files in os.walk(mcp_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for f in files:
                fp = Path(root) / f
                if fp.suffix.lower() == ".json":
                    assets["Level_2_System_Settings"].append(fp)

    # 2. Workspace scan (Level_1, Level_4, Level_5)
    candidates = [
        custom_ws,
        user_home / "Documents" / "AI_Workspace",
        user_home / "Projects",
        user_home / "Workspace"
    ]
    ws_dir = None
    for c in candidates:
        if c and Path(c).exists():
            ws_dir = Path(c).resolve()
            break

    if ws_dir:
        assets["ws_scan"] = ws_dir
        for root, dirs, files in os.walk(ws_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for f in files:
                fp = Path(root) / f
                f_name = f.lower()
                if any(pat in f_name for pat in [".env", "token.json", "secret", "credentials"]):
                    continue

                if f in ("AGENTS.md", "CLAUDE.md", ".cursorrules", ".clinerules"):
                    assets["Level_1_Agent_Directives"].append(fp)
                else:
                    try:
                        sz_mb = fp.stat().st_size / (1024 * 1024)
                        if sz_mb > 10.0 or fp.suffix.lower() in [".mp4", ".mov", ".avi", ".iso", ".dmg", ".tar", ".gz"]:
                            assets["Level_5_Heavy_References"].append((fp, sz_mb))
                        else:
                            assets["Level_4_Workspace_Docs"].append(fp)
                    except Exception:
                        pass

    # Core Neural Hub size calculation (Level_1 + Level_2 + Level_3)
    s1 = sum(f.stat().st_size for f in assets["Level_1_Agent_Directives"] if f.exists())
    s2 = sum(f.stat().st_size for f in assets["Level_2_System_Settings"] if f.exists())
    s3 = sum(f.stat().st_size for f in assets["Level_3_Modular_Skills"] if f.exists())
    assets["t_core_mb"] = (s1 + s2 + s3) / (1024 * 1024)

    return assets
