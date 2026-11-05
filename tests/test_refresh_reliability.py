import copy
import hashlib
import json
import unittest
from tools.catalog_refresh import needs_build
from tools.verify_public_catalog import verify_once, verify_with_retry


class RefreshReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.payload = b'{"schema":1,"source":"usda","records":[]}'
        self.manifest = {
            "schema": 1, "catalogVersion": "test",
            "sources": {"usda": {"records": 2, "release": "2026-10-29"}},
            "assets": {name: {"records": 1, "bytes": len(self.payload), "sha256": hashlib.sha256(self.payload).hexdigest()}
                       for name in ("usda-search-ab.json", "usda-barcode-00.json")},
        }
        self.raw = json.dumps(self.manifest).encode()

    def test_unchanged_source_skips_rebuild(self):
        self.assertFalse(needs_build(self.manifest, "2026-10-29"))

    def test_new_source_builds(self):
        self.assertTrue(needs_build(self.manifest, "2026-11-30"))

    def test_explicit_force_rebuilds_same_source(self):
        self.assertTrue(needs_build(self.manifest, "2026-10-29", True))

    def test_old_discovery_cannot_downgrade_even_with_force(self):
        for force in (False, True):
            with self.assertRaises(ValueError):
                needs_build(self.manifest, "2026-04-30", force)

    def test_invalid_manifest_is_not_silently_treated_as_new_source(self):
        for field in ("assets", "schema"):
            bad = copy.deepcopy(self.manifest)
            bad[field] = None
            with self.assertRaises(ValueError):
                needs_build(bad, "2026-11-30")

    def test_public_manifest_and_both_lookup_paths_are_checked(self):
        urls = []
        def fetch(url):
            urls.append(url)
            return self.raw if url.endswith("manifest.json") else self.payload
        self.assertEqual(verify_once(self.raw, "https://example.test", fetch), "test")
        self.assertEqual(len(urls), 3)
        self.assertTrue(any("search-" in url for url in urls))
        self.assertTrue(any("barcode-" in url for url in urls))

    def test_stale_manifest_fails(self):
        with self.assertRaises(ValueError):
            verify_once(self.raw, "https://example.test", lambda url: b'{}')

    def test_corrupt_shard_fails(self):
        with self.assertRaises(ValueError):
            verify_once(self.raw, "https://example.test", lambda url: self.raw if url.endswith("manifest.json") else b'wrong')

    def test_temporary_stale_cache_retries_and_recovers(self):
        attempts = []
        def fetch(url):
            if url.endswith("manifest.json"):
                attempts.append(1)
                return b'{}' if len(attempts) == 1 else self.raw
            return self.payload
        sleeps = []
        self.assertEqual(verify_with_retry(self.raw, "https://example.test", 2, 1, fetch, sleeps.append), "test")
        self.assertEqual(sleeps, [1])

    def test_persistent_failure_is_not_reported_as_success(self):
        with self.assertRaises(ValueError):
            verify_with_retry(self.raw, "https://example.test", 2, 0, lambda url: b'{}', lambda _: None)


if __name__ == "__main__":
    unittest.main()
