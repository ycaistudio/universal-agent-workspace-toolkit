"""Size-capped packages: split, re-join, and never-overwrite output names.

A package that fits under the part cap is written exactly as before: one
``<stem>.zip``. A larger package becomes standalone zips named
``<stem>_Part_01_of_03.zip``. These are not multi-volume archives. Each part
opens on its own in Windows Explorer or any unzip tool, keeps relative paths,
and carries its own ``package_manifest.json`` slice.

A file larger than one part is stored as pieces named
``<path>.uawt-chunk-001-of-003``. Every part manifest lists all pieces under
``split.chunked_files``, so restore can re-join them and check the SHA-256 of
the whole file. Sizes here are decimal megabytes (1 MB = 1,000,000 bytes).
"""

import copy
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

MB = 1000 * 1000
DEFAULT_PART_MB = 90
HARD_MAX_PART_MB = 95
DEFAULT_PART_BYTES = DEFAULT_PART_MB * MB
HARD_MAX_PART_BYTES = HARD_MAX_PART_MB * MB
LONG_PATH_LIMIT = 200
MANIFEST_NAME = "package_manifest.json"
CHUNK_TAG = ".uawt-chunk-"
PART_RE = re.compile(r"^(?P<stem>.+)_Part_(?P<part>\d+)_of_(?P<parts>\d+)\.zip(?P<enc>\.enc)?$")
_BLOCK = 1024 * 1024


class PartError(Exception):
    """The package cannot be written under the requested part cap."""


def validate_part_mb(value):
    """Return the part cap in bytes. Reject values above 95 MB or not above 0."""
    try:
        mb = float(value)
    except (TypeError, ValueError):
        raise PartError(f"--max-part-mb must be a number, got {value!r}")
    if mb != mb or mb <= 0:
        raise PartError("--max-part-mb must be greater than 0")
    if mb > HARD_MAX_PART_MB:
        raise PartError(f"--max-part-mb must not exceed {HARD_MAX_PART_MB} (decimal MB)")
    return int(mb * MB)


def unique_stem(directory, stem, part_count=1):
    """Return a stem whose outputs do not exist yet: stem, stem_v2, stem_v3, ...

    Both ``.zip`` and ``.zip.enc`` names count as taken, for the single file and
    for every part name, so an earlier kit is never overwritten.
    """
    directory = Path(directory)
    candidate, version = stem, 1
    while True:
        names = [f"{candidate}.zip"] + [
            part_name(candidate, index, part_count) for index in range(1, part_count + 1)
        ] if part_count > 1 else [f"{candidate}.zip"]
        if not any((directory / n).exists() or (directory / (n + ".enc")).exists() for n in names):
            return candidate
        version += 1
        candidate = f"{stem}_v{version}"


def part_name(stem, index, count):
    width = max(2, len(str(count)))
    return f"{stem}_Part_{index:0{width}d}_of_{count:0{width}d}.zip"


def chunk_name(rel, index, count):
    return f"{rel}{CHUNK_TAG}{index:03d}-of-{count:03d}"


def long_path_report(names, limit=LONG_PATH_LIMIT):
    """Longest archive path. Advice is set when it is longer than ``limit`` characters."""
    names = list(names)
    longest = max((len(n) for n in names), default=0)
    report = {"max_path_chars": longest, "limit": limit, "over_limit": longest > limit}
    if longest > limit:
        over = sorted((n for n in names if len(n) > limit), key=len, reverse=True)
        report["count_over_limit"] = len(over)
        report["examples"] = over[:5]
        report["advice"] = (
            "Paths in this kit are longer than {0} characters. On Windows, extract near the "
            "drive root (for example C:\\GB\\) or enable LongPathsEnabled "
            "(HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem)."
        ).format(limit)
    return report


def _estimate(size, name):
    # Deflate can grow incompressible data a little; headers repeat the name twice.
    return size + size // 1000 + 256 + 2 * len(name.encode("utf-8"))


def _hash_slice(path, offset, length):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        handle.seek(offset)
        left = length
        while left > 0:
            block = handle.read(min(_BLOCK, left))
            if not block:
                break
            digest.update(block)
            left -= len(block)
    return digest.hexdigest()


def _plan(entries, budget):
    """Group (rel, size) entries into parts. Large files become pieces."""
    parts, current, used = [], [], 0
    for rel, size in entries:
        cost = _estimate(size, rel)
        if cost <= budget - used:
            current.append(("file", rel, 0, size))
            used += cost
            continue
        if cost <= budget:
            parts.append(current)
            current, used = [("file", rel, 0, size)], cost
            continue
        piece = int((budget - 256 - 2 * len(chunk_name(rel, 1, 1).encode("utf-8")) - 4096) / 1.001)
        if piece <= 0:
            raise PartError("The part cap is too small for this file name.")
        if current:
            parts.append(current)
        offsets = list(range(0, size, piece))
        for offset in offsets:
            length = min(piece, size - offset)
            current = [("chunk", rel, offset, length)]
            used = _estimate(length, chunk_name(rel, 1, 1))
            if offset != offsets[-1]:
                parts.append(current)
    if current:
        parts.append(current)
    return [part for part in parts if part]


def _chmod_private(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def write_package(staging_dir, manifest_doc, packages_dir, stem,
                  max_part_bytes=DEFAULT_PART_BYTES, private=False):
    """Write the staged tree as one zip or as standalone parts. Return the zip paths.

    ``manifest_doc["file_manifest"]`` must list every staged file. The doc gets
    ``long_paths`` and ``max_part_bytes``; split output also gets ``split``.
    """
    if max_part_bytes > HARD_MAX_PART_BYTES:
        raise PartError(f"Part cap above {HARD_MAX_PART_MB} MB is not allowed.")
    staging_dir, packages_dir = Path(staging_dir), Path(packages_dir)
    file_manifest = manifest_doc["file_manifest"]
    entries = sorted((rel, meta["size"]) for rel, meta in file_manifest.items())
    manifest_doc["max_part_bytes"] = max_part_bytes
    reserve = len(json.dumps(manifest_doc, indent=2, ensure_ascii=False).encode("utf-8")) + 64 * 1024
    if reserve * 2 > max_part_bytes:
        raise PartError("The manifest alone is too large for this part cap. Raise --max-part-mb.")
    budget = max_part_bytes - reserve
    total = sum(_estimate(size, rel) for rel, size in entries)

    if total <= budget:
        manifest_doc["long_paths"] = long_path_report(list(file_manifest) + [MANIFEST_NAME])
        zip_path = packages_dir / f"{unique_stem(packages_dir, stem)}.zip"
        (staging_dir / MANIFEST_NAME).write_text(
            json.dumps(manifest_doc, indent=2, ensure_ascii=False), encoding="utf-8")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            for root, _, files in os.walk(staging_dir):
                for name in files:
                    path = Path(root) / name
                    zipf.write(path, arcname=path.relative_to(staging_dir).as_posix())
        _verify_written(zip_path, list(file_manifest), max_part_bytes)
        if private:
            _chmod_private(zip_path)
        return [zip_path]

    parts = _plan(entries, budget)
    count = len(parts)
    stem = unique_stem(packages_dir, stem, count)
    names = [part_name(stem, index, count) for index in range(1, count + 1)]

    chunked = {}
    for index, part in enumerate(parts, start=1):
        for kind, rel, offset, length in part:
            if kind == "chunk":
                chunked.setdefault(rel, []).append({"part": index, "offset": offset, "size": length})
    for rel, pieces in chunked.items():
        for number, piece in enumerate(pieces, start=1):
            piece["name"] = chunk_name(rel, number, len(pieces))
            piece["sha256"] = _hash_slice(staging_dir / rel, piece["offset"], piece["size"])
    chunked_files = {
        rel: {
            "size": file_manifest[rel]["size"],
            "sha256": file_manifest[rel]["sha256"],
            "level": file_manifest[rel].get("level"),
            "pieces": [{k: piece[k] for k in ("name", "part", "size", "sha256")} for piece in pieces],
        }
        for rel, pieces in chunked.items()
    }
    piece_lookup = {(rel, piece["offset"]): piece for rel, pieces in chunked.items() for piece in pieces}
    arc_names = [rel for rel in file_manifest if rel not in chunked]
    arc_names += [piece["name"] for pieces in chunked.values() for piece in pieces]
    manifest_doc["long_paths"] = long_path_report(arc_names + [MANIFEST_NAME])

    written = []
    for index, part in enumerate(parts, start=1):
        doc = copy.copy(manifest_doc)
        slice_ = {}
        for kind, rel, offset, length in part:
            if kind == "file":
                slice_[rel] = file_manifest[rel]
            else:
                piece = piece_lookup[(rel, offset)]
                slice_[piece["name"]] = {"size": length, "sha256": piece["sha256"],
                                         "level": file_manifest[rel].get("level"), "chunk_of": rel}
        doc["file_manifest"] = slice_
        doc["split"] = {
            "set_id": manifest_doc["tracking_id"],
            "part": index,
            "parts": count,
            "part_names": names,
            "chunked_files": chunked_files,
        }
        zip_path = packages_dir / names[index - 1]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            for kind, rel, offset, length in part:
                if kind == "file":
                    zipf.write(staging_dir / rel, arcname=rel)
                    continue
                piece = piece_lookup[(rel, offset)]
                with open(staging_dir / rel, "rb") as src, zipf.open(piece["name"], "w", force_zip64=True) as dst:
                    src.seek(offset)
                    left = length
                    while left > 0:
                        block = src.read(min(_BLOCK, left))
                        if not block:
                            break
                        dst.write(block)
                        left -= len(block)
            zipf.writestr(MANIFEST_NAME, json.dumps(doc, indent=2, ensure_ascii=False))
        _verify_written(zip_path, list(slice_), max_part_bytes)
        if private:
            _chmod_private(zip_path)
        written.append(zip_path)
    return written


def _verify_written(zip_path, expected, max_part_bytes):
    with zipfile.ZipFile(zip_path, "r") as zipf:
        present = set(zipf.namelist())
    for rel in expected:
        if rel not in present:
            raise RuntimeError(f"Integrity check failed: missing {rel} in zip!")
    size = Path(zip_path).stat().st_size
    if size > max_part_bytes:
        raise PartError(f"{Path(zip_path).name} is {size} bytes, above the cap of {max_part_bytes} bytes.")


# ---------------------------------------------------------------- restore side
def sibling_parts(path):
    """All files in the same folder that belong to the same part set as ``path``."""
    path = Path(path)
    match = PART_RE.match(path.name)
    if not match:
        return [path]
    found = []
    for other in path.parent.iterdir():
        m = PART_RE.match(other.name)
        if m and m.group("stem") == match.group("stem") and m.group("parts") == match.group("parts") \
                and bool(m.group("enc")) == bool(match.group("enc")):
            found.append(other)
    return sorted(found)


def join_chunks(staging_dir, file_manifest, chunked_files, verified):
    """Re-join pieces in ``staging_dir``. Return (final_manifest, corrupted).

    ``verified`` is the set of piece names whose SHA-256 already matched.
    Pieces are removed after a successful join.
    """
    staging_dir = Path(staging_dir).resolve()
    final = {rel: meta for rel, meta in file_manifest.items() if "chunk_of" not in meta}
    corrupted = []
    for rel, info in sorted(chunked_files.items()):
        target = (staging_dir / rel).resolve()
        if staging_dir not in target.parents:
            corrupted.append((rel, "unsafe path"))
            continue
        missing = [p["name"] for p in info["pieces"] if p["name"] not in verified]
        if missing:
            corrupted.append((rel, f"split file incomplete ({len(missing)} piece(s) missing or damaged)"))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with open(target, "wb") as out:
            for piece in info["pieces"]:
                with open(staging_dir / piece["name"], "rb") as src:
                    while True:
                        block = src.read(_BLOCK)
                        if not block:
                            break
                        digest.update(block)
                        out.write(block)
        for piece in info["pieces"]:
            (staging_dir / piece["name"]).unlink()
        if digest.hexdigest() != info["sha256"]:
            corrupted.append((rel, "SHA-256 mismatch after re-join"))
            continue
        final[rel] = {"size": info["size"], "sha256": info["sha256"], "level": info.get("level")}
    return final, corrupted
