"""
Universal AI Agent Workspace Toolkit - Asset & Credential Scanner (toolkit_scanner.py)

One classifier decides what may be packed. It is applied to every level, so the
Level_0 report and the packer can never disagree about what was scanned.

Default policy (personal migration tool):
  - Known credential file types, private keys and real-format tokens are NOT packed.
  - MCP JSON is packed with secret values replaced by a placeholder.
  - Prose that merely mentions "password" or "token" is reported but still packed.
  - include_secrets=True (explicit user opt-in) packs everything as-is.
What the user does with the finished package is the user's responsibility.
"""

import os
import re
import sys
import json
import hashlib
from pathlib import Path

REDACTED = "__REDACTED_RESTORE_MANUALLY__"


def win_p(p):
    s = str(Path(p).resolve())
    if sys.platform == "win32":
        prefix = "\\\\?\\"
        if not s.startswith(prefix) and not s.startswith("\\\\"):
            return prefix + s
    return s


def calculate_sha256(fp):
    h = hashlib.sha256()
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

# ---------------------------------------------------------------- classification
SECRET_NAMES = {
    "id_rsa", "id_ed25519", "id_ecdsa", "auth.json", "token.json",
    "secrets.json", ".netrc", "credentials", "credentials.json",
}
SECRET_SUFFIXES = (".kdbx", ".p12", ".pfx")
KEY_SUFFIXES = (".pem", ".key")  # secret only if the content holds a private key block

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
HIGH_CONF_RE = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{36}"
    r"|\bsk-[A-Za-z0-9_-]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"
)
WEAK_RE = re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\b\s*(?:[:=]|is\b)\s*\S+")
MAX_SCAN_BYTES = 2 * 1024 * 1024


def _read_text(fp):
    """Return file text for scanning, or None for large / binary files."""
    try:
        if Path(fp).stat().st_size > MAX_SCAN_BYTES:
            return None
        with open(win_p(fp), "rb") as f:
            raw = f.read()
        if b"\0" in raw[:8192]:
            return None
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return None


def classify_file(fp, content_scan=True):
    """Return ("exclude" | "warn" | "ok", reason). Reasons never contain file contents."""
    name = Path(fp).name.lower()
    if name in SECRET_NAMES or name.startswith(".env") or name.endswith(SECRET_SUFFIXES):
        return "exclude", f"credential file type ({Path(fp).name})"

    needs_text = content_scan or name.endswith(KEY_SUFFIXES)
    text = _read_text(fp) if needs_text else None
    if text is None:
        return "ok", ""

    if PRIVATE_KEY_RE.search(text):
        return "exclude", "contains a private key block"
    if not content_scan:
        return "ok", ""
    if HIGH_CONF_RE.search(text):
        return "exclude", "contains a real-format API token"
    if WEAK_RE.search(text):
        return "warn", "mentions a password/token value (packed; review it)"
    return "ok", ""


# ---------------------------------------------------------------- MCP redaction
SECRET_KEY_RE = re.compile(r"(?i)(token|secret|passw(or)?d|api[_-]?key|authorization|credential|private[_-]?key|bearer)")
CONTAINER_KEYS = {"env", "headers"}


URL_CRED_RE = re.compile(r"(?<=://)([^/\s:@]+):([^/\s@]+)(?=@)")


def _scrub_str(v):
    """Replace real-format tokens and user:password@ URL credentials inside a string."""
    v, n1 = HIGH_CONF_RE.subn(REDACTED, v)
    v, n2 = URL_CRED_RE.subn(lambda m: f"{m.group(1)}:{REDACTED}", v)
    return v, n1 + n2


def _redact(node, in_container=False):
    """Return (new_node, replaced_count). Server definitions (command, args, url) are kept.

    Every string value under "env" or "headers" is replaced (safest default: the tool cannot tell
    which environment values are secret). Other strings are only scrubbed for token formats and URL passwords.
    """
    count = 0
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            kl = str(k).lower()
            if isinstance(v, str) and v and (in_container or SECRET_KEY_RE.search(kl)):
                out[k] = REDACTED
                count += 1
            elif isinstance(v, (dict, list)):
                out[k], c = _redact(v, in_container or kl in CONTAINER_KEYS)
                count += c
            elif isinstance(v, str):
                out[k], c = _scrub_str(v)
                count += c
            else:
                out[k] = v
        return out, count
    if isinstance(node, list):
        out = []
        for v in node:
            if isinstance(v, (dict, list)):
                nv, c = _redact(v, in_container)
            elif isinstance(v, str):
                nv, c = _scrub_str(v)
            else:
                nv, c = v, 0
            out.append(nv)
            count += c
        return out, count
    return node, 0


def redact_mcp_json(text):
    """Return (redacted_json_text, replaced_count). Raises ValueError if the JSON cannot be parsed."""
    data = json.loads(text)
    out, count = _redact(data)
    return json.dumps(out, indent=2, ensure_ascii=False), count


# ---------------------------------------------------------------- asset scan
def resolve_workspace(user_home, custom_ws=None):
    """Resolve the workspace directory exactly once; every later step uses this result."""
    for c in (custom_ws, user_home / "Documents" / "AI_Workspace", user_home / "Projects", user_home / "Workspace"):
        if c and Path(c).exists():
            return Path(c).resolve()
    return None


def scan_all_assets(user_home, custom_ws=None, include_secrets=False):
    """Scan system + workspace, classify into Level_1..Level_5, and apply the secret policy once."""
    assets = {
        "Level_1_Agent_Directives": [],
        "Level_2_System_Settings": [],
        "Level_3_Modular_Skills": [],
        "Level_4_Workspace_Docs": [],
        "Level_5_Heavy_References": [],
        "skills_names": [],
        "ws_scan": None,
        "excluded": [],   # (path, reason) - never packed
        "flagged": [],    # (path, reason) - packed but worth reviewing
        "include_secrets": include_secrets,
        "sizes_mb": {},
        "t_core_mb": 0.0,
    }

    def admit(fp, level_key, content_scan=True, extra=None):
        """Apply the secret policy; append to the level list unless excluded."""
        if not include_secrets:
            verdict, reason = classify_file(fp, content_scan=content_scan)
            if verdict == "exclude":
                assets["excluded"].append((fp, reason))
                return
            if verdict == "warn":
                assets["flagged"].append((fp, reason))
        assets[level_key].append(extra if extra is not None else fp)

    # Level_3 skills
    skills_dir = user_home / ".gemini" / "config" / "skills"
    if skills_dir.exists():
        for d in skills_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                assets["skills_names"].append(d.name)
                for root, dirs, files in os.walk(d):
                    dirs[:] = [sub for sub in dirs if sub not in EXCLUDED_DIRS]
                    for f in files:
                        admit(Path(root) / f, "Level_3_Modular_Skills")

    # Level_2 MCP definitions (secret values are redacted by the packer, so no content scan here)
    mcp_dir = user_home / ".gemini" / "antigravity" / "mcp"
    if mcp_dir.exists():
        for root, dirs, files in os.walk(mcp_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for f in files:
                fp = Path(root) / f
                if fp.suffix.lower() == ".json":
                    admit(fp, "Level_2_System_Settings", content_scan=False)

    # Workspace: Level_1 directives, Level_4 docs, Level_5 heavy references
    ws_dir = resolve_workspace(user_home, custom_ws)
    if ws_dir:
        assets["ws_scan"] = ws_dir
        for root, dirs, files in os.walk(ws_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for f in files:
                fp = Path(root) / f
                if f in ("AGENTS.md", "CLAUDE.md", ".cursorrules", ".clinerules"):
                    admit(fp, "Level_1_Agent_Directives")
                    continue
                try:
                    sz_mb = fp.stat().st_size / (1024 * 1024)
                except Exception:
                    continue
                if sz_mb > 10.0 or fp.suffix.lower() in (".mp4", ".mov", ".avi", ".iso", ".dmg", ".tar", ".gz"):
                    admit(fp, "Level_5_Heavy_References", content_scan=False, extra=(fp, sz_mb))
                else:
                    admit(fp, "Level_4_Workspace_Docs")

    # Real sizes per level (what the audit table prints)
    for key in ("Level_1_Agent_Directives", "Level_2_System_Settings", "Level_3_Modular_Skills", "Level_4_Workspace_Docs"):
        total = 0
        for f in assets[key]:
            try:
                total += f.stat().st_size
            except Exception:
                pass
        assets["sizes_mb"][key] = total / (1024 * 1024)
    assets["sizes_mb"]["Level_5_Heavy_References"] = sum(sz for _, sz in assets["Level_5_Heavy_References"])
    assets["t_core_mb"] = sum(assets["sizes_mb"][k] for k in (
        "Level_1_Agent_Directives", "Level_2_System_Settings", "Level_3_Modular_Skills"))
    return assets
