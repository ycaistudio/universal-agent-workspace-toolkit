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
KEY_SUFFIXES = (".pem", ".key")  # excluded by name (v2.3.0); the file is not opened

# v2.3.0 name gate. Matching is by file name only, so the file is never read.
# Exact names that are always credential stores.
SECRET_EXACT_NAMES = {"gateway.json", "mcp_config.json"}
# Broad name patterns. They skip documentation and source files, so a note such as
# secretariat_minutes.md or a script named token_counter.py is still packed.
SECRET_NAME_PATTERNS = (
    ("secret", re.compile(r"secret(?!ar)")),       # *secret*, but not secretary / secretariat
    ("token", re.compile(r"token(?!iz)")),         # *token*, but not tokenizer*
    ("credential", re.compile(r"credential")),     # *credential*
    ("cookie", re.compile(r"cookie")),             # *cookie*
)
KEY_JSON_RE = re.compile(r"(?:^|[^a-z])(?:api[_-]?)?keys?(?:[^a-z]|$)")  # *key*.json, not keybindings.json
DOC_SUFFIXES = {
    ".md", ".markdown", ".rst", ".adoc", ".py", ".pyi", ".ipynb", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".scss", ".sh", ".ps1", ".bat",
    ".java", ".kt", ".go", ".rs", ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift",
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
}
# Packed as-is and never caught by the name gate (tokenizer files, package lockfiles).
LOCKFILE_NAMES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "composer.lock",
    "cargo.lock",
    "poetry.lock",
    "gemfile.lock",
    "packages.lock.json",
    "tokenizer_config.json",
    "tokenizer.json",
}
SECRET_DIR_NAMES = {"credentials", ".credentials"}

# v2.3.0 model weights: not packed unless --include-bulky.
MODEL_SUFFIXES = (".onnx", ".pt", ".pth", ".ckpt", ".safetensors", ".gguf")
MODEL_BIN_SUFFIXES = (".bin",)
MODEL_MIN_BYTES = 5 * 1000 * 1000

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


def secret_name_reason(fp, broad=True):
    """Name-only credential check. Returns a reason or None; the file is never opened.

    ``broad=False`` keeps only the v2.2.0 exact names (used for MCP folders whose
    values are redacted instead of dropped).
    """
    name = Path(fp).name.lower()
    shown = Path(fp).name
    if name in SECRET_NAMES or name.startswith(".env") or name.endswith(SECRET_SUFFIXES):
        return f"credential file type ({shown})"
    if not broad or name in LOCKFILE_NAMES:
        return None
    if name in SECRET_EXACT_NAMES:
        return f"credential file name ({shown})"
    if name.endswith(KEY_SUFFIXES):
        return f"key or certificate file ({shown}); not opened"
    suffix = Path(name).suffix
    if suffix in DOC_SUFFIXES:
        return None
    for label, pattern in SECRET_NAME_PATTERNS:
        if pattern.search(name):
            return f"credential-like file name (*{label}*: {shown}); not opened"
    if suffix == ".json" and KEY_JSON_RE.search(Path(name).stem):
        return f"credential-like file name (*key*.json: {shown}); not opened"
    return None


def secret_dir_reason(name):
    """Directories that are skipped whole: credentials/ and .credentials/."""
    if str(name).lower() in SECRET_DIR_NAMES:
        return f"credential directory ({name}/); not opened"
    return None


def venv_dir_reason(path, name):
    """Virtual environments and installed packages. Their requirements are frozen instead."""
    lowered = str(name).lower()
    if lowered == "site-packages":
        return "site-packages directory"
    try:
        if (Path(path) / "pyvenv.cfg").is_file():
            return "virtualenv (pyvenv.cfg)"
    except OSError:
        return "unreadable directory"
    if "venv" in lowered:
        return "virtualenv-like directory (*venv*)"
    return None


def model_weight_reason(fp, size):
    """Model weights are left out unless --include-bulky."""
    name = Path(fp).name.lower()
    if name.endswith(MODEL_SUFFIXES) and size >= MODEL_MIN_BYTES:
        return "model weights (pass --include-bulky to pack)"
    if name.endswith(MODEL_BIN_SUFFIXES) and size >= MODEL_MIN_BYTES:
        return "large .bin, likely model weights (pass --include-bulky to pack)"
    return None


def classify_file(fp, content_scan=True, warn_weak=True, broad_names=True):
    """Return ("exclude" | "warn" | "ok", reason). Reasons never contain file contents."""
    name = Path(fp).name.lower()
    reason = secret_name_reason(fp, broad=broad_names)
    if reason:
        return "exclude", reason

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
    if warn_weak and WEAK_RE.search(text):
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


def scan_all_assets(user_home, custom_ws=None, include_secrets=False, include_bulky=False):
    """Scan system + workspace, classify into Level_1..Level_5, and apply the secret policy once.

    v2.3.0: credentials/ folders and credential-like names are excluded by name,
    virtualenvs are skipped and recorded in ``venvs`` (their requirements are
    frozen at pack time), and model weights go to Level 5 unless include_bulky.
    """
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
        "include_bulky": include_bulky,
        "venvs": [],      # virtualenv folders that were skipped
        "skipped": [],    # (path, reason) - directories not walked
        "sizes_mb": {},
        "t_core_mb": 0.0,
    }

    def keep_dirs(root, dirs):
        """Filter os.walk dirs in place and record why a folder was left out."""
        kept = []
        for sub in dirs:
            full = Path(root) / sub
            if sub in EXCLUDED_DIRS:
                if sub in (".venv", "venv") and (full / "pyvenv.cfg").is_file():
                    assets["venvs"].append(full)
                continue
            reason = None if include_secrets else secret_dir_reason(sub)
            if reason:
                assets["excluded"].append((full, reason))
                continue
            reason = venv_dir_reason(full, sub)
            if reason:
                assets["skipped"].append((full, reason))
                if reason.startswith("virtualenv"):
                    assets["venvs"].append(full)
                continue
            kept.append(sub)
        dirs[:] = kept

    def admit(fp, level_key, content_scan=True, extra=None, broad_names=True):
        """Apply the secret policy; append to the level list unless excluded."""
        if not include_secrets:
            verdict, reason = classify_file(fp, content_scan=content_scan, broad_names=broad_names)
            if verdict == "exclude":
                assets["excluded"].append((fp, reason))
                return
            if verdict == "warn":
                assets["flagged"].append((fp, reason))
        if not include_bulky and level_key != "Level_5_Heavy_References":
            try:
                size = Path(fp).stat().st_size
            except OSError:
                size = 0
            if model_weight_reason(fp, size):
                assets["Level_5_Heavy_References"].append((fp, size / (1024 * 1024)))
                return
        assets[level_key].append(extra if extra is not None else fp)

    # Level_3 skills
    skills_dir = user_home / ".gemini" / "config" / "skills"
    if skills_dir.exists():
        for d in skills_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                assets["skills_names"].append(d.name)
                for root, dirs, files in os.walk(d):
                    keep_dirs(root, dirs)
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
                    # MCP values are redacted by the packer, so only the exact v2.2.0 names drop a file here.
                    admit(fp, "Level_2_System_Settings", content_scan=False, broad_names=False)

    # Workspace: Level_1 directives, Level_4 docs, Level_5 heavy references
    ws_dir = resolve_workspace(user_home, custom_ws)
    if ws_dir:
        assets["ws_scan"] = ws_dir
        for root, dirs, files in os.walk(ws_dir):
            keep_dirs(root, dirs)
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
    # Same skill or rules tree in more than one place: the user picks the canonical copy.
    from toolkit_preflight import find_duplicates
    assets["duplicates"] = find_duplicates(
        assets["Level_1_Agent_Directives"] + assets["Level_3_Modular_Skills"] + assets["Level_4_Workspace_Docs"],
        display=lambda p: _home_display(p, user_home))
    return assets


def _home_display(path, user_home):
    try:
        return "~/" + Path(path).resolve().relative_to(Path(user_home).resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)
