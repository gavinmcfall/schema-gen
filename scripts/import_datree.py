#!/usr/bin/env python3
"""
Import schemas from datreeio/CRDs-catalog as a seed.

This script fetches existing schemas from the datree catalog and converts
them to our directory structure: {group}/{version}/{kind}.json

Usage:
    python import_datree.py --output schemas/
    python import_datree.py --output schemas/ --groups cert-manager.io,helm.toolkit.fluxcd.io
"""

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

DATREE_API = "https://api.github.com/repos/datreeio/CRDs-catalog/contents"
DATREE_RAW = "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main"


def fetch_json(url: str) -> dict | list | None:
    """Fetch JSON from URL."""
    try:
        with urlopen(url) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        print(f"  Error fetching {url}: {e}")
        return None


def fetch_text(url: str) -> str | None:
    """Fetch text from URL."""
    try:
        with urlopen(url) as response:
            return response.read().decode()
    except HTTPError as e:
        print(f"  Error fetching {url}: {e}")
        return None


def list_api_groups() -> list[str]:
    """List all API groups in the datree catalog."""
    contents = fetch_json(DATREE_API)
    if not contents:
        return []

    groups = []
    for item in contents:
        name = item.get("name", "")
        # Skip non-directory items and special files
        if item.get("type") != "dir":
            continue
        if name.startswith(".") or name == "Utilities":
            continue
        if name[0].isupper():  # Skip files like README, LICENSE
            continue
        groups.append(name)

    return sorted(groups)


def list_schemas_in_group(group: str) -> list[str]:
    """List all schema files in an API group."""
    url = f"{DATREE_API}/{group}"
    contents = fetch_json(url)
    if not contents:
        return []

    schemas = []
    for item in contents:
        name = item.get("name", "")
        if name.endswith(".json"):
            schemas.append(name)

    return schemas


def parse_schema_filename(filename: str) -> tuple[str, str] | None:
    """
    Parse datree filename format: {kind}_{version}.json
    Returns (kind, version) or None if invalid.
    """
    if not filename.endswith(".json"):
        return None

    name = filename[:-5]  # Remove .json

    # Handle special cases like _v1, _v1beta1, _v2alpha1
    match = re.match(r"^(.+)_(v\d+(?:alpha\d+|beta\d+)?)$", name)
    if match:
        return match.group(1).lower(), match.group(2)

    return None


def transform_schema(schema: dict, group: str, version: str, kind: str) -> dict:
    """Transform schema to our format with updated $id."""
    # Update $id to our domain
    schema["$id"] = f"https://k8s-schemas.io/{group}/{version}/{kind}.json"

    # Ensure $schema is set
    if "$schema" not in schema:
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"

    return schema


def import_schema(group: str, schema_file: str, output_dir: Path) -> bool:
    """Import a single schema file."""
    parsed = parse_schema_filename(schema_file)
    if not parsed:
        return False

    kind, version = parsed

    # Fetch the schema
    url = f"{DATREE_RAW}/{group}/{schema_file}"
    content = fetch_text(url)
    if not content:
        return False

    try:
        schema = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  Error parsing {schema_file}: {e}")
        return False

    # Transform and write
    schema = transform_schema(schema, group, version, kind)

    out_path = output_dir / group / version / f"{kind}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(schema, f, indent=2)

    return True


def import_group(group: str, output_dir: Path) -> int:
    """Import all schemas from an API group. Returns count of imported schemas."""
    print(f"Importing: {group}")

    schemas = list_schemas_in_group(group)
    if not schemas:
        print("  No schemas found")
        return 0

    count = 0
    for schema_file in schemas:
        if import_schema(group, schema_file, output_dir):
            count += 1

    print(f"  Imported {count} schemas")
    return count


def main():
    parser = argparse.ArgumentParser(description="Import schemas from datreeio/CRDs-catalog")
    parser.add_argument("--output", default="schemas", help="Output directory")
    parser.add_argument("--groups", help="Comma-separated list of groups to import (default: all)")
    parser.add_argument("--list", action="store_true", help="Just list available groups")
    parser.add_argument("--parallel", type=int, default=5, help="Parallel import workers")

    args = parser.parse_args()

    print("Fetching API groups from datreeio/CRDs-catalog...")
    all_groups = list_api_groups()
    print(f"Found {len(all_groups)} API groups")

    if args.list:
        for group in all_groups:
            print(f"  {group}")
        return

    # Determine which groups to import
    if args.groups:
        groups = [g.strip() for g in args.groups.split(",")]
        # Validate
        invalid = set(groups) - set(all_groups)
        if invalid:
            print(f"Warning: Unknown groups: {invalid}")
        groups = [g for g in groups if g in all_groups]
    else:
        groups = all_groups

    print(f"Importing {len(groups)} groups...")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = 0

    # Import in parallel
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {executor.submit(import_group, group, output_dir): group for group in groups}
        for future in as_completed(futures):
            group = futures[future]
            try:
                count = future.result()
                total += count
            except Exception as e:
                print(f"Error importing {group}: {e}")

    print(f"\nTotal schemas imported: {total}")


if __name__ == "__main__":
    main()
