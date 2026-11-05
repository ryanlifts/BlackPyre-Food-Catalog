#!/usr/bin/env python3
"""Verify the consumer-facing mirror, without mistaking an old catalog for success."""
import argparse
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path


def sample_assets(manifest):
    assets = manifest.get("assets", {})
    selected = []
    for prefix in ("usda-search-", "usda-barcode-"):
        names = sorted(name for name in assets if name.startswith(prefix))
        if not names:
            raise ValueError(f"Missing {prefix} assets")
        # A large representative shard exercises each consumer lookup path.
        name = max(names, key=lambda name: assets[name]["records"])
        if not re.fullmatch(r"usda-(search|barcode)-[a-z0-9]{2}\.json", name):
            raise ValueError("Unsafe shard name")
        selected.append(name)
    return selected


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "BlackPyreCatalogVerifier/1.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read()


def verify_once(expected_bytes, base_url, fetcher=fetch):
    expected = json.loads(expected_bytes)
    public = fetcher(base_url.rstrip("/") + "/manifest.json")
    if public != expected_bytes:
        raise ValueError("Public manifest does not match the deployed release yet")
    for name in sample_assets(expected):
        payload = fetcher(base_url.rstrip("/") + "/" + name)
        metadata = expected["assets"][name]
        if len(payload) != metadata["bytes"] or hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
            raise ValueError(f"Public shard does not match release: {name}")
    return expected["catalogVersion"]


def verify_with_retry(expected_bytes, base_url, attempts=20, delay=45, fetcher=fetch, sleeper=time.sleep):
    for attempt in range(attempts):
        try:
            return verify_once(expected_bytes, base_url, fetcher)
        except Exception as error:
            if attempt == attempts - 1:
                raise
            print(f"Public verification attempt {attempt + 1} failed: {error}; retrying", flush=True)
            sleeper(delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    if not args.base_url.startswith("https://ryanlifts.github.io/BlackPyre-Food-Catalog"):
        raise ValueError("Unexpected public catalog URL")
    version = verify_with_retry(args.manifest.read_bytes(), args.base_url)
    print(f"Public catalog verified: {version}; manifest and search/barcode sample hashes match")


if __name__ == "__main__":
    main()
