# BlackPyre Food Catalog

BlackPyre's no-cost, downloadable food-data pipeline. It turns public USDA
FoodData Central all-data-types bulk downloads into small JSON shards that BlackPyre can
search without a paid server or an API key.

## Data contract

- USDA records remain identified as `usda` and retain their FoodData Central ID.
- Open Food Facts remains a separately identified live fallback inside
  BlackPyre; it is never relabeled or merged into the USDA catalog.
- The app may present one search experience, but the source datasets are never
  merged into a new unlabeled database.
- Source attribution is retained so BlackPyre can distinguish catalog nutrition
  from nutrition the user has checked against a package label.

## Release assets

`manifest.json` describes the current catalog and every published shard.
Search shards are selected by the first two normalized characters of a product
or brand token. Barcode shards are selected by the first two barcode digits.

The weekly scheduled workflow checks USDA for a newer all-data-types CSV. It reuses
the current catalog when that source is already published. When USDA updates it, the
workflow downloads the archive, builds and validates every shard, and publishes
a dated GitHub Release only after every asset succeeds. The app uses
GitHub's stable `releases/latest/download/manifest.json` URL and caches shards
locally for offline reuse.

## Reliable refresh and publication

- Every Monday at 09:17 UTC, refresh runs its tests and discovers the official
  USDA source. GitHub may delay scheduled jobs.
- A source older than the published catalog is rejected. A failed manifest
  download fails visibly rather than causing an unnecessary rebuild.
- Publication is a required reusable job in the refresh workflow, not a separate
  completion-event handoff. It mirrors the latest complete release to Pages,
  validating every asset before deployment.
- After deployment, the normal public manifest must match the release exactly.
  Representative search and barcode shards must match their byte counts and
  SHA-256 hashes. Verification retries temporary cache delays and fails if the
  public files remain stale or corrupt.
- Each refresh attempt commits `status/catalog-check.json` on the dedicated
  `catalog-status` branch, including outcomes,
  the run URL, and the last successful refresh/publication time. These meaningful
  weekly audit commits keep the repository active even when USDA is unchanged,
  addressing GitHub's 60-day inactivity shutdown for public scheduled workflows
  without bypassing the pull-request protection on `main`.
  Failed jobs remain failed; a failed attempt does not advance `lastSuccessAt`.

Consumer endpoints remain unchanged:

- Native app: <https://github.com/ryanlifts/BlackPyre-Food-Catalog/releases/latest/download/manifest.json>
- Web mirror: <https://ryanlifts.github.io/BlackPyre-Food-Catalog/manifest.json>

To recover a failure, inspect the linked run in the status file and rerun failed
jobs after correcting its cause. **Refresh BlackPyre Food Catalog → Run workflow**
checks the current source and republishes; enable `force_rebuild` only when the
current source needs rebuilding. **Publish Food Catalog to GitHub Pages → Run
workflow** repairs the mirror without rebuilding. If GitHub disables scheduling,
re-enable the refresh workflow first. This has no independent external watchdog:
account restrictions, a disabled workflow, or GitHub outages can still stop runs.

Before changing the pipeline, run `python3 -m unittest discover -s tests`.

## Local build

```sh
python3 tools/build_catalog.py \
  --usda-zip FoodData_Central_csv_2026-04-30.zip \
  --output dist \
  --release-tag catalog-2026-04-30
python3 tools/validate_catalog.py dist
```

USDA FoodData Central data is public domain under CC0. Open Food Facts data is
available under ODbL; see `licenses/` and the manifest source metadata.
