"""Pre-pack checks added in v2.3.0: virtualenv requirement locks and duplicate rule trees.

Virtualenvs are never copied into a kit. Instead each one is frozen with its own
interpreter (``uv pip freeze`` when uv is installed, else ``python -m pip freeze``)
so the target machine can rebuild it. Nothing here touches the network.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

LOCK_DIR = "python-envs"
FREEZE_TIMEOUT = 60
RULE_FILES = ("SKILL.md", "AGENTS.md", "CLAUDE.md", ".cursorrules", ".clinerules")
_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _offline_env():
    env = dict(os.environ)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["UV_OFFLINE"] = "1"
    env["UV_NO_PROGRESS"] = "1"
    return env


def venv_python(venv):
    """The venv's own interpreter, or None."""
    venv = Path(venv)
    for rel in (("bin", "python"), ("bin", "python3"), ("Scripts", "python.exe")):
        candidate = venv.joinpath(*rel)
        if candidate.is_file():
            return candidate
    return None


def _run(cmd):
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=FREEZE_TIMEOUT,
                              env=_offline_env(), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, type(exc).__name__
    if done.returncode != 0:
        return None, f"exit {done.returncode}"
    return done.stdout, None


def freeze_venv(venv):
    """Return (requirements_text, tool, error). Tries uv first, then pip, both offline."""
    python = venv_python(venv)
    if python is None:
        return None, None, "no python interpreter found in the virtualenv"
    errors = []
    uv = shutil.which("uv")
    if uv:
        out, err = _run([uv, "pip", "freeze", "--python", str(python), "--offline"])
        if out is not None:
            return out, "uv pip freeze", None
        errors.append(f"uv: {err}")
    out, err = _run([str(python), "-m", "pip", "freeze", "--disable-pip-version-check"])
    if out is not None:
        return out, "pip freeze", None
    errors.append(f"pip: {err}")
    return None, None, "; ".join(errors)


def _lock_name(venv, home=None, used=None):
    venv = Path(venv)
    label = venv.name
    parent = venv.parent.name
    if parent:
        label = f"{parent}_{label}"
    label = _SAFE_RE.sub("_", label).strip("_") or "venv"
    name = f"requirements-{label}.txt"
    used = used if used is not None else set()
    n = 2
    while name in used:
        name = f"requirements-{label}_{n}.txt"
        n += 1
    used.add(name)
    return name


def emit_env_locks(venvs, dest_dir, display=str, include_user=True):
    """Write requirements files for each virtualenv into ``dest_dir``.

    Returns a manifest-ready dict. File contents are package lists only; no
    environment variables or paths are written into them.
    """
    dest_dir = Path(dest_dir)
    report = {"venvs": [], "user_packages": None}
    used = set()
    seen = set()
    for venv in venvs:
        venv = Path(venv)
        try:
            key = venv.resolve()
        except OSError:
            key = venv
        if key in seen:
            continue
        seen.add(key)
        entry = {"path": display(venv)}
        text, tool, error = freeze_venv(venv)
        if text is None:
            entry["status"] = "failed"
            entry["error"] = error
        else:
            name = _lock_name(venv, used=used)
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / name).write_text(text, encoding="utf-8")
            entry.update(status="ok", tool=tool, file=f"{LOCK_DIR}/{name}",
                         packages=sum(1 for line in text.splitlines() if line.strip() and not line.startswith("#")))
        report["venvs"].append(entry)
    if include_user:
        out, err = _run([sys.executable, "-m", "pip", "list", "--user", "--format=freeze",
                         "--disable-pip-version-check"])
        if out is not None:
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / "pip-user-packages.txt").write_text(out, encoding="utf-8")
            report["user_packages"] = {"status": "ok", "file": f"{LOCK_DIR}/pip-user-packages.txt",
                                       "packages": sum(1 for line in out.splitlines() if line.strip())}
        else:
            report["user_packages"] = {"status": "failed", "error": err}
    return report


# ---------------------------------------------------------------- duplicate trees
def _sha(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(65536), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def _tree_signature(folder):
    """Hash of the top-level files in a folder (name + content)."""
    digest = hashlib.sha256()
    try:
        names = sorted(p.name for p in Path(folder).iterdir() if p.is_file() and not p.is_symlink())
    except OSError:
        return None
    for name in names:
        digest.update(name.encode("utf-8") + b"\0" + (_sha(Path(folder) / name) or "").encode("ascii") + b"\0")
    return digest.hexdigest()


def find_duplicates(rule_files, display=str):
    """Find the same skill or rules tree in more than one place.

    ``rule_files`` are paths that will be packed. Returns a list of groups:
    ``identical`` (same file content in several folders; ``identical_tree`` is
    True when the folders' top-level files also match) and ``diverged`` (same
    skill folder name, different SKILL.md). The caller asks which copy is canonical.
    """
    by_hash, by_skill = {}, {}
    for path in rule_files:
        path = Path(path)
        if path.name not in RULE_FILES:
            continue
        digest = _sha(path)
        if digest is None:
            continue
        by_hash.setdefault((path.name, digest), []).append(path)
        if path.name == "SKILL.md":
            by_skill.setdefault(path.parent.name, {}).setdefault(digest, []).append(path)
    groups = []
    for (name, digest), paths in sorted(by_hash.items(), key=lambda kv: (kv[0][0], str(kv[1][0]))):
        parents = sorted({p.parent for p in paths}, key=str)
        if len(parents) < 2:
            continue
        signatures = {_tree_signature(p) for p in parents}
        groups.append({
            "kind": "identical",
            "file": name,
            "sha256": digest,
            "identical_tree": len(signatures) == 1,
            "locations": [display(p) for p in parents],
        })
    for skill, variants in sorted(by_skill.items()):
        if len(variants) < 2:
            continue
        locations = sorted(display(p.parent) for paths in variants.values() for p in paths)
        groups.append({"kind": "diverged", "file": "SKILL.md", "skill": skill, "locations": locations})
    return groups
