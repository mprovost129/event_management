#!/usr/bin/env python3
"""Create a clean source ZIP without secrets, caches, logs, or local data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXCLUDED_DIRS = {
    ".git",
    ".github-cache",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__MACOSX",
    "node_modules",
    "venv",
}
EXCLUDED_NAMES = {
    ".DS_Store",
    ".env",
    "db.sqlite3",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}


def should_include(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_DIRS or part.startswith("._") for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES or path.name.startswith(".env."):
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if "media" in relative.parts and path.name != ".gitkeep":
        return False
    if "logs" in relative.parts and path.name != ".gitkeep":
        return False
    return path.is_file()


def create_archive(root: Path, output: Path) -> int:
    files = sorted(path for path in root.rglob("*") if should_include(path, root))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, arcname=Path(root.name) / path.relative_to(root))
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dist/gatherhqs-source.zip"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output == root or root in output.parents and output.is_dir():
        raise SystemExit("Output must be a ZIP file, not a source directory.")
    count = create_archive(root, output)
    print(f"Created {output} with {count} files.")


if __name__ == "__main__":
    main()
