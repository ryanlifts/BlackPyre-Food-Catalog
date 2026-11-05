#!/usr/bin/env python3
"""Decide whether a known, readable catalog needs rebuilding."""
import argparse
import json
from datetime import date
from pathlib import Path


def needs_build(manifest, source_date, force=False):
    current = manifest["sources"]["usda"]
    if manifest.get("schema") != 1 or not current.get("records") or not manifest.get("assets"):
        raise ValueError("The published catalog manifest is invalid or empty")
    discovered = date.fromisoformat(source_date)
    published = date.fromisoformat(current["release"])
    if discovered < published:
        raise ValueError("USDA discovery is older than the published source; refusing a downgrade")
    return force or discovered > published


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["decide"])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--force", choices=["true", "false"], default="false")
    args = parser.parse_args()
    build = needs_build(json.loads(args.manifest.read_text()), args.source_date, args.force == "true")
    print(f"build={str(build).lower()}")


if __name__ == "__main__":
    main()
