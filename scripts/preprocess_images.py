#!/usr/bin/env python3
"""Preprocess microscopy images: rename and copy into a flat output folder.

Finds .jpg/.jpeg files under input directories, renames files matching
"{id}_Orig.{ext}" to "sub-{id}_original.{ext}" and copies them into
the output directory.

Usage:
  python3 scripts/preprocess_images.py

Defaults:
  inputs: data/Even Illuminated Macro Images, data/raw/Uneven Illuminated Macro Images
  output: data/processed

Only uses Python standard library.
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import List


PATTERN = re.compile(r"^(?P<id>\d+)_Orig\.(?P<ext>jpe?g)$", re.IGNORECASE)


def find_image_files(dirs: List[Path]) -> List[Path]:
    files = []
    for d in dirs:
        if not d.exists():
            print(f"Warning: input directory does not exist: {d}")
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}:
                files.append(p)
    return files


def make_target_name(orig_name: str) -> str | None:
    m = PATTERN.match(orig_name)
    if not m:
        return None
    id_ = m.group("id")
    ext = m.group("ext").lower()
    return f"sub-{id_}_original.{ext}"


def unique_target_path(base: Path, name: str) -> Path:
    candidate = base / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while True:
        new_name = f"{stem}_{i}{suffix}"
        candidate = base / new_name
        if not candidate.exists():
            return candidate
        i += 1


def process(inputs: List[Path], output: Path, dry_run: bool = False) -> dict:
    stats = {
        "files_found": 0,
        "matched": 0,
        "copied": 0,
        "skipped": 0,
        "skipped_details": [],
    }

    files = find_image_files(inputs)
    stats["files_found"] = len(files)

    if not dry_run:
        output.mkdir(parents=True, exist_ok=True)

    for p in files:
        name = p.name
        target_name = make_target_name(name)
        if not target_name:
            stats["skipped"] += 1
            stats["skipped_details"].append((str(p), "pattern_mismatch"))
            print(f"Skipping (pattern mismatch): {p}")
            continue

        stats["matched"] += 1
        target_path = output / target_name
        if target_path.exists():
            # Disambiguate by adding numeric suffix
            new_target = unique_target_path(output, target_name)
            print(f"Name collision for {target_name}; using {new_target.name}")
            target_path = new_target

        if dry_run:
            print(f"Would copy: {p} -> {target_path}")
            stats["copied"] += 1
        else:
            try:
                shutil.copy2(p, target_path)
                stats["copied"] += 1
                print(f"Copied: {p} -> {target_path}")
            except Exception as e:
                stats["skipped"] += 1
                stats["skipped_details"].append((str(p), f"copy_failed:{e}"))
                print(f"Failed to copy {p}: {e}")

    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preprocess microscopy images by renaming and copying into a flat output folder")
    parser.add_argument("--input-dirs", nargs="+", default=[
        "data/Even Illuminated Macro Images",
        "data/raw/Uneven Illuminated Macro Images",
    ], help="Input directories to search recursively for .jpg files")
    parser.add_argument("--output-dir", default="data/processed", help="Output directory to write renamed copies")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without copying files")
    args = parser.parse_args(argv)

    input_paths = [Path(p) for p in args.input_dirs]
    output_path = Path(args.output_dir)

    print("Input directories:")
    for p in input_paths:
        print(f" - {p}")
    print(f"Output directory: {output_path}")
    if args.dry_run:
        print("Dry run: no files will be copied")

    stats = process(input_paths, output_path, dry_run=args.dry_run)

    print("\nSummary:")
    print(f"  Files with image extension found: {stats['files_found']}")
    print(f"  Files matching pattern and processed: {stats['matched']}")
    print(f"  Files copied (or would be copied in dry-run): {stats['copied']}")
    print(f"  Files skipped: {stats['skipped']}")
    if stats['skipped_details']:
        print("  Skip reasons:")
        for fp, reason in stats['skipped_details']:
            print(f"    - {fp}: {reason}")


if __name__ == "__main__":
    main()
