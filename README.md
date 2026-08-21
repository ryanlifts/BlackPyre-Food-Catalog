# BlackPyre Food Catalog

BlackPyre's no-cost, downloadable food-data pipeline. It turns public USDA
FoodData Central bulk downloads into small JSON shards that BlackPyre can
search without a paid server or an API key.

## Data contract

- USDA records remain identified as `usda` and retain their FoodData Central ID.
- Open Food Facts remains a separately identified live fallback inside
  BlackPyre; it is never relabeled or merged into the USDA catalog.
- The app may present one search experience, but the source datasets are never
  merged into a new unlabeled database.
- Every result remains subject to package-label verification before logging.

## Release assets

`manifest.json` describes the current catalog and every published shard.
Search shards are selected by the first two normalized characters of a product
or brand token. Barcode shards are selected by the first two barcode digits.

The monthly scheduled workflow checks USDA for a newer branded CSV and does
nothing when the current source is already published. When USDA updates it, the
workflow downloads the archive, builds and validates every shard, and publishes
a dated GitHub Release only after every asset succeeds. The app uses
GitHub's stable `releases/latest/download/manifest.json` URL and caches shards
locally for offline reuse.

## Local build

```sh
python3 tools/build_catalog.py \
  --usda-zip FoodData_Central_branded_food_csv_2026-04-30.zip \
  --output dist \
  --release-tag catalog-2026-04-30
python3 tools/validate_catalog.py dist
```

USDA FoodData Central data is public domain under CC0. Open Food Facts data is
available under ODbL; see `licenses/` and the manifest source metadata.
