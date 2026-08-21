#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
fixtures = root / "tests" / "fixtures"

with tempfile.TemporaryDirectory(prefix="blackpyre-catalog-test-") as temp:
    temp_path = Path(temp)
    archive = temp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for name in ("food.csv", "branded_food.csv", "food_nutrient.csv"):
            output.write(fixtures / name, f"FoodData_Central_test/{name}")
    dist = temp_path / "dist"
    subprocess.run(
        [
            "python3", str(root / "tools" / "build_catalog.py"),
            "--usda-zip", str(archive),
            "--output", str(dist),
            "--release-tag", "catalog-test",
            "--source-date", "2026-04-30",
        ],
        check=True,
    )
    subprocess.run(["python3", str(root / "tools" / "validate_catalog.py"), str(dist)], check=True)
    manifest = json.loads((dist / "manifest.json").read_text())
    assert manifest["recordCount"] == 3
    assert manifest["sources"]["usda"]["records"] == 3
    assert manifest["sources"]["usda"]["dataTypes"] == "all USDA FoodData Central data types"
    assert "usda-barcode-00.json" in manifest["assets"]
    search = json.loads((dist / "usda-search-te.json").read_text())
    record = search["records"][0]
    assert record[1] == "TEST VANILLA YOGURT"
    assert record[2] == "Test Brand"
    assert record[3:7] == [59.0, 10.0, 3.6, 0.4]
    chicken = json.loads((dist / "usda-search-ch.json").read_text())["records"][0]
    assert chicken[1] == "CHICKEN BREAST MEAT ONLY COOKED ROASTED"
    assert chicken[2] == ""
    assert chicken[3:7] == [165.0, 31.02, 0.0, 3.57]
    assert chicken[7:10] == [100.0, "100 g", ""]

print("catalog fixture test passed")
