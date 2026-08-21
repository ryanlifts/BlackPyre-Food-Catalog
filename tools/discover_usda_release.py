#!/usr/bin/env python3
"""Discover the newest official USDA all-data-types bulk CSV archive."""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin


DOWNLOADS_PAGE = "https://fdc.nal.usda.gov/download-datasets/"
ARCHIVE_PATTERN = re.compile(
    r"(?P<url>(?:https?://fdc\.nal\.usda\.gov)?/fdc-datasets/"
    r"FoodData_Central_csv_(?P<date>\d{4}-\d{2}-\d{2})\.zip)"
)


@dataclass(frozen=True)
class Release:
    source_date: str
    url: str


def discover(document: str) -> Release:
    decoded = html.unescape(document).replace("\\/", "/")
    matches = [
        Release(match.group("date"), urljoin(DOWNLOADS_PAGE, match.group("url")))
        for match in ARCHIVE_PATTERN.finditer(decoded)
    ]
    if not matches:
        raise RuntimeError("USDA downloads page did not expose the all-data-types CSV archive")
    return max(matches, key=lambda release: release.source_date)


def fetch_page() -> str:
    request = urllib.request.Request(
        DOWNLOADS_PAGE,
        headers={"User-Agent": "BlackPyreFoodCatalog/1.0 blackpyrestrong@gmail.com"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"USDA downloads page returned HTTP {response.status}")
        return response.read().decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, help="Use a saved downloads page instead of the network")
    parser.add_argument("--github-env", type=Path, help="Append USDA_URL and USDA_SOURCE_DATE")
    args = parser.parse_args()
    release = discover(args.html.read_text() if args.html else fetch_page())
    values = f"USDA_URL={release.url}\nUSDA_SOURCE_DATE={release.source_date}\n"
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as output:
            output.write(values)
    else:
        sys.stdout.write(values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
