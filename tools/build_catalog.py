#!/usr/bin/env python3
"""Build source-separated BlackPyre food catalog shards from USDA bulk CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

SCHEMA = 1
NUTRIENTS = {
    "1008": "cal",   # Energy (kcal), legacy identifier
    "2047": "cal",   # Energy (Atwater General Factors)
    "2048": "cal",   # Energy (Atwater Specific Factors)
    "1003": "pro",
    "1005": "carb",
    "1004": "fat",
}


def clean_text(value: object, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def normalized_barcode(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 13 and digits.startswith("0"):
        digits = digits[1:]
    return digits if 8 <= len(digits) <= 14 else ""


def normalized_token(value: object) -> str:
    folded = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", ascii_text.lower())


def prefixes(name: str, brand: str) -> set[str]:
    found: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", f"{name} {brand}".lower()):
        token = normalized_token(token)
        if len(token) >= 2:
            found.add(token[:2])
    return found


def float_or_none(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 100000:
        return None
    return round(number, 4)


def source_zip(path_or_url: str, temp_dir: Path) -> Path:
    if re.match(r"^https://", path_or_url):
        target = temp_dir / "usda.zip"
        request = urllib.request.Request(
            path_or_url,
            headers={"User-Agent": "BlackPyre-Food-Catalog/1.0 (blackpyrestrong@gmail.com)"},
        )
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out)
        return target
    return Path(path_or_url).expanduser().resolve()


def member_name(archive: zipfile.ZipFile, suffix: str) -> str:
    matches = [name for name in archive.namelist() if name.lower().endswith(suffix.lower())]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {suffix} in USDA archive; found {matches}")
    return matches[0]


def dict_rows(archive: zipfile.ZipFile, member: str):
    with archive.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        yield from csv.DictReader(text)


def initialize_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=MEMORY;
        CREATE TABLE foods (
          fdc_id INTEGER PRIMARY KEY,
          name TEXT NOT NULL DEFAULT '',
          brand TEXT NOT NULL DEFAULT '',
          barcode TEXT NOT NULL DEFAULT '',
          serving REAL,
          serving_unit TEXT NOT NULL DEFAULT '',
          serving_label TEXT NOT NULL DEFAULT '',
          modified TEXT NOT NULL DEFAULT '',
          country TEXT NOT NULL DEFAULT '',
          cal REAL,
          pro REAL,
          carb REAL,
          fat REAL
        );
        CREATE INDEX foods_barcode ON foods(barcode);
        """
    )
    return connection


def load_usda(archive_path: Path, database_path: Path) -> sqlite3.Connection:
    connection = initialize_database(database_path)
    with zipfile.ZipFile(archive_path) as archive:
        branded_member = member_name(archive, "/branded_food.csv")
        food_member = member_name(archive, "/food.csv")
        nutrient_member = member_name(archive, "/food_nutrient.csv")

        batch = []
        for row in dict_rows(archive, branded_member):
            barcode = normalized_barcode(row.get("gtin_upc"))
            if not barcode:
                continue
            country = clean_text(row.get("market_country"), 80)
            # BlackPyre 1.0 serves the U.S.; excluding clearly non-U.S. products
            # keeps mobile shards useful and substantially smaller.
            if country and "united states" not in country.lower():
                continue
            serving = float_or_none(row.get("serving_size"))
            batch.append(
                (
                    int(row["fdc_id"]),
                    clean_text(row.get("brand_name") or row.get("brand_owner"), 100),
                    barcode,
                    serving,
                    clean_text(row.get("serving_size_unit"), 16),
                    clean_text(row.get("household_serving_fulltext"), 100),
                    clean_text(row.get("modified_date") or row.get("available_date"), 20),
                    country,
                )
            )
            if len(batch) >= 10_000:
                connection.executemany(
                    "INSERT OR REPLACE INTO foods(fdc_id,brand,barcode,serving,serving_unit,serving_label,modified,country) VALUES(?,?,?,?,?,?,?,?)",
                    batch,
                )
                connection.commit()
                batch.clear()
        if batch:
            connection.executemany(
                "INSERT OR REPLACE INTO foods(fdc_id,brand,barcode,serving,serving_unit,serving_label,modified,country) VALUES(?,?,?,?,?,?,?,?)",
                batch,
            )
            connection.commit()

        batch = []
        for row in dict_rows(archive, food_member):
            batch.append((clean_text(row.get("description"), 180), int(row["fdc_id"])))
            if len(batch) >= 20_000:
                connection.executemany("UPDATE foods SET name=? WHERE fdc_id=?", batch)
                connection.commit()
                batch.clear()
        if batch:
            connection.executemany("UPDATE foods SET name=? WHERE fdc_id=?", batch)
            connection.commit()

        batch = []
        for row in dict_rows(archive, nutrient_member):
            field = NUTRIENTS.get(str(row.get("nutrient_id") or ""))
            if not field:
                continue
            amount = float_or_none(row.get("amount"))
            if amount is None:
                continue
            batch.append((amount, int(row["fdc_id"]), field))
            if len(batch) >= 25_000:
                for nutrient_field in ("cal", "pro", "carb", "fat"):
                    values = [(amount, fdc_id) for amount, fdc_id, current in batch if current == nutrient_field]
                    connection.executemany(f"UPDATE foods SET {nutrient_field}=? WHERE fdc_id=?", values)
                connection.commit()
                batch.clear()
        if batch:
            for nutrient_field in ("cal", "pro", "carb", "fat"):
                values = [(amount, fdc_id) for amount, fdc_id, current in batch if current == nutrient_field]
                connection.executemany(f"UPDATE foods SET {nutrient_field}=? WHERE fdc_id=?", values)
            connection.commit()
    return connection


def compact_record(row: sqlite3.Row) -> list:
    serving = row["serving"]
    serving_unit = clean_text(row["serving_unit"], 16).lower()
    serving_g = serving if serving and serving > 0 and serving_unit in {"g", "gram", "grams", "ml"} else None
    serving_label = clean_text(row["serving_label"], 100)
    if not serving_label and serving and serving > 0:
        serving_label = f"{serving:g} {serving_unit}".strip()
    return [
        str(row["fdc_id"]),
        clean_text(row["name"], 180),
        clean_text(row["brand"], 100),
        row["cal"],
        row["pro"],
        row["carb"],
        row["fat"],
        serving_g,
        serving_label,
        row["barcode"],
        clean_text(row["modified"], 20),
    ]


def write_json(path: Path, value: object) -> tuple[int, str]:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    path.write_bytes(payload)
    return len(payload), hashlib.sha256(payload).hexdigest()


def write_catalog(connection: sqlite3.Connection, output: Path, release_tag: str, source_date: str) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT * FROM foods
        WHERE name<>'' AND barcode<>''
          AND cal IS NOT NULL AND pro IS NOT NULL AND carb IS NOT NULL AND fat IS NOT NULL
          AND cal BETWEEN 0 AND 1000 AND pro BETWEEN 0 AND 100
          AND carb BETWEEN 0 AND 100 AND fat BETWEEN 0 AND 100
        ORDER BY barcode, modified DESC, fdc_id DESC
        """
    )

    search_shards: dict[str, list] = defaultdict(list)
    barcode_shards: dict[str, list] = defaultdict(list)
    seen_barcodes: set[str] = set()
    count = 0
    for row in rows:
        if row["barcode"] in seen_barcodes:
            continue
        seen_barcodes.add(row["barcode"])
        record = compact_record(row)
        barcode_shards[row["barcode"][:2]].append(record)
        for prefix in prefixes(row["name"], row["brand"]):
            search_shards[prefix].append(record)
        count += 1

    assets = {}
    for prefix, records in sorted(search_shards.items()):
        filename = f"usda-search-{prefix}.json"
        size, digest = write_json(output / filename, {"schema": SCHEMA, "source": "usda", "records": records})
        assets[filename] = {"bytes": size, "sha256": digest, "records": len(records)}
    for prefix, records in sorted(barcode_shards.items()):
        filename = f"usda-barcode-{prefix}.json"
        size, digest = write_json(output / filename, {"schema": SCHEMA, "source": "usda", "records": records})
        assets[filename] = {"bytes": size, "sha256": digest, "records": len(records)}

    release_base = f"https://github.com/ryanlifts/BlackPyre-Food-Catalog/releases/download/{release_tag}"
    manifest = {
        "schema": SCHEMA,
        "catalogVersion": release_tag.removeprefix("catalog-"),
        "releaseTag": release_tag,
        "releaseBase": release_base,
        "generated": date.today().isoformat(),
        "sources": {
            "usda": {
                "label": "USDA FoodData Central",
                "release": source_date,
                "license": "CC0-1.0",
                "url": "https://fdc.nal.usda.gov/",
                "records": count,
            },
            "off": {
                "label": "Open Food Facts",
                "mode": "source-separated live fallback",
                "license": "ODbL-1.0",
                "url": "https://world.openfoodfacts.org/",
            },
        },
        "searchPrefixLength": 2,
        "barcodePrefixLength": 2,
        "searchPrefixes": sorted(search_shards),
        "barcodePrefixes": sorted(barcode_shards),
        "assets": assets,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usda-zip", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-date", default="2026-04-30")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="blackpyre-food-catalog-") as temp:
        temp_dir = Path(temp)
        archive = source_zip(args.usda_zip, temp_dir)
        connection = load_usda(archive, temp_dir / "catalog.sqlite")
        manifest = write_catalog(connection, Path(args.output), args.release_tag, args.source_date)
        connection.close()
    print(json.dumps({"records": manifest["sources"]["usda"]["records"], "assets": len(manifest["assets"])}))


if __name__ == "__main__":
    main()
