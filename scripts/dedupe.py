#!/usr/bin/env python3
"""
Schema deduplication and metadata management.

This module handles:
1. Content-hash based deduplication
2. Source provenance tracking
3. Canonical source selection

Usage:
    python dedupe.py --schemas-dir schemas/ --report
    python dedupe.py --schemas-dir schemas/ --dedupe
"""

import argparse
from collections import defaultdict
from pathlib import Path

from common import compute_schema_hash, load_schema, save_schema

# Priority order for canonical sources (lower = higher priority)
# When same schema exists from multiple sources, prefer the "official" one
SOURCE_PRIORITY = {
    # Official operator sources (highest priority)
    "cert-manager": 1,
    "external-secrets": 1,
    "flux": 1,
    "gateway-api": 1,
    "prometheus-operator-crds": 1,
    "kube-prometheus-stack": 2,  # Bundles prometheus-operator
    # Cloud providers
    "ack-": 1,  # AWS ACK (prefix match)
    "azure-service-operator": 1,
    "config-connector": 1,
    # Datree import (lower priority - use as fallback)
    "datree": 10,
    # Default
    "default": 5,
}


def get_source_priority(source_name: str) -> int:
    """Get priority for a source (lower = higher priority)."""
    # Check exact match
    if source_name in SOURCE_PRIORITY:
        return SOURCE_PRIORITY[source_name]

    # Check prefix match
    for prefix, priority in SOURCE_PRIORITY.items():
        if prefix.endswith("-") and source_name.startswith(prefix):
            return priority

    return SOURCE_PRIORITY["default"]


def scan_schemas(schemas_dir: Path) -> dict:
    """
    Scan all schemas and group by API path.

    Returns: {
        "cert-manager.io/v1/certificate": [
            {"path": Path, "schema": dict, "hash": str, "source": str},
            ...
        ]
    }
    """
    schemas = defaultdict(list)

    for json_file in schemas_dir.rglob("*.json"):
        if json_file.name == "index.json":
            continue

        try:
            schema = load_schema(json_file)
        except Exception:
            print(f"Warning: Invalid JSON in {json_file}")
            continue

        # Extract API path from file path: {group}/{version}/{kind}.json
        rel_path = json_file.relative_to(schemas_dir)
        parts = rel_path.parts

        if len(parts) != 3:
            continue

        group, version, kind_file = parts
        kind = kind_file.replace(".json", "")
        api_path = f"{group}/{version}/{kind}"

        # Get source from metadata
        metadata = schema.get("x-kubernetes-schema-metadata", {})
        source = metadata.get("sourceName", "unknown")
        source_version = metadata.get("sourceVersion", "unknown")

        schemas[api_path].append(
            {
                "path": json_file,
                "schema": schema,
                "hash": compute_schema_hash(schema),
                "source": source,
                "source_version": source_version,
            }
        )

    return schemas


def find_duplicates(schemas: dict) -> dict:
    """Find schemas that exist from multiple sources."""
    duplicates = {}

    for api_path, entries in schemas.items():
        if len(entries) > 1:
            duplicates[api_path] = entries

    return duplicates


def report_duplicates(schemas_dir: Path):
    """Report on duplicate schemas."""
    print(f"Scanning {schemas_dir}...")
    schemas = scan_schemas(schemas_dir)

    total_schemas = sum(len(entries) for entries in schemas.values())
    unique_apis = len(schemas)

    print(f"\nTotal schema files: {total_schemas}")
    print(f"Unique API paths: {unique_apis}")

    duplicates = find_duplicates(schemas)

    if not duplicates:
        print("\nNo duplicates found!")
        return

    print(f"\nDuplicates found: {len(duplicates)} API paths\n")

    for api_path, entries in sorted(duplicates.items()):
        print(f"  {api_path}:")

        # Group by hash
        by_hash = defaultdict(list)
        for entry in entries:
            by_hash[entry["hash"]].append(entry)

        if len(by_hash) == 1:
            print(f"    └─ IDENTICAL content from {len(entries)} sources:")
        else:
            print(f"    └─ DIFFERENT content ({len(by_hash)} variants):")

        for hash_val, hash_entries in by_hash.items():
            sources = [f"{e['source']}@{e['source_version']}" for e in hash_entries]
            print(f"       [{hash_val}] {', '.join(sources)}")


def dedupe_schemas(schemas_dir: Path, dry_run: bool = True):
    """
    Deduplicate schemas, keeping the highest priority source.

    For schemas with identical content: keep highest priority, delete others
    For schemas with different content: keep all, add hash suffix
    """
    print(f"Scanning {schemas_dir}...")
    schemas = scan_schemas(schemas_dir)
    duplicates = find_duplicates(schemas)

    if not duplicates:
        print("No duplicates to process.")
        return

    actions = []

    for api_path, entries in duplicates.items():
        # Group by hash
        by_hash = defaultdict(list)
        for entry in entries:
            by_hash[entry["hash"]].append(entry)

        if len(by_hash) == 1:
            # All identical - keep highest priority
            sorted_entries = sorted(entries, key=lambda e: get_source_priority(e["source"]))
            keep = sorted_entries[0]
            remove = sorted_entries[1:]

            actions.append(
                {
                    "type": "dedupe_identical",
                    "api_path": api_path,
                    "keep": keep,
                    "remove": remove,
                }
            )
        else:
            # Different content - this is more complex
            # For now, just report and keep all
            actions.append(
                {
                    "type": "different_content",
                    "api_path": api_path,
                    "variants": dict(by_hash),
                }
            )

    # Execute actions
    print(f"\nProcessing {len(actions)} duplicate groups...")

    for action in actions:
        if action["type"] == "dedupe_identical":
            keep = action["keep"]
            remove = action["remove"]

            print(f"\n  {action['api_path']}:")
            print(f"    KEEP: {keep['source']}@{keep['source_version']}")

            for entry in remove:
                print(f"    {'WOULD DELETE' if dry_run else 'DELETE'}: {entry['source']}@{entry['source_version']}")
                if not dry_run:
                    entry["path"].unlink()

        elif action["type"] == "different_content":
            print(f"\n  {action['api_path']}: {len(action['variants'])} different versions (keeping all)")

    if dry_run:
        print("\n[DRY RUN - no files modified. Use --execute to apply changes]")


def add_provenance(schemas_dir: Path, source_name: str, source_version: str):
    """Add provenance metadata to schemas missing it."""
    print(f"Adding provenance: source={source_name}, version={source_version}")

    count = 0
    for json_file in schemas_dir.rglob("*.json"):
        if json_file.name == "index.json":
            continue

        try:
            schema = load_schema(json_file)
        except Exception:
            continue

        # Check if already has metadata
        if "x-kubernetes-schema-metadata" in schema:
            continue

        # Add metadata
        schema["x-kubernetes-schema-metadata"] = {
            "sourceName": source_name,
            "sourceVersion": source_version,
        }

        save_schema(json_file, schema)
        count += 1

    print(f"Updated {count} schemas")


def main():
    parser = argparse.ArgumentParser(description="Schema deduplication")
    parser.add_argument("--schemas-dir", default="schemas", help="Schemas directory")
    parser.add_argument("--report", action="store_true", help="Report duplicates")
    parser.add_argument("--dedupe", action="store_true", help="Deduplicate (dry run)")
    parser.add_argument("--execute", action="store_true", help="Actually delete duplicates")
    parser.add_argument(
        "--add-provenance", nargs=2, metavar=("SOURCE", "VERSION"), help="Add provenance to schemas without it"
    )

    args = parser.parse_args()
    schemas_dir = Path(args.schemas_dir)

    if args.report:
        report_duplicates(schemas_dir)
    elif args.dedupe or args.execute:
        dedupe_schemas(schemas_dir, dry_run=not args.execute)
    elif args.add_provenance:
        add_provenance(schemas_dir, args.add_provenance[0], args.add_provenance[1])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
