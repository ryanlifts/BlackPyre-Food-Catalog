#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"catalog validation failed: {message}")


root = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
manifest_path = root / "manifest.json"
if not manifest_path.is_file():
    fail("manifest.json is missing")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if manifest.get("schema") != 1:
    fail("unsupported schema")
if not manifest.get("sources", {}).get("usda", {}).get("records"):
    fail("USDA catalog is empty")

for name, expected in manifest.get("assets", {}).items():
    path = root / name
    if not path.is_file():
        fail(f"missing asset {name}")
    payload = path.read_bytes()
    if len(payload) != expected.get("bytes"):
        fail(f"wrong byte count for {name}")
    if hashlib.sha256(payload).hexdigest() != expected.get("sha256"):
        fail(f"wrong hash for {name}")
    shard = json.loads(payload)
    if shard.get("schema") != 1 or shard.get("source") != "usda":
        fail(f"bad header in {name}")
    if len(shard.get("records", [])) != expected.get("records"):
        fail(f"wrong record count for {name}")
    for record in shard.get("records", []):
        if len(record) != 11 or not record[1]:
            fail(f"malformed record in {name}")
        if name.startswith("usda-barcode-") and not record[9]:
            fail(f"barcode shard contains a generic record in {name}")
        if any(value is None or value < 0 for value in record[3:7]):
            fail(f"invalid nutrition in {name}")

print(f"catalog valid: {manifest['sources']['usda']['records']} USDA foods, {len(manifest['assets'])} assets")
