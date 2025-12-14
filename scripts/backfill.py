#!/usr/bin/env python3
"""
Backfill historical versions for CRD sources.

This script discovers all available versions for a source and extracts
CRDs from each version, building a complete historical record.

Usage:
    python backfill.py --source cert-manager --output schemas/
    python backfill.py --source cert-manager --output schemas/ --min-version 1.0.0
    python backfill.py --all --output schemas/
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import yaml
from common import (
    crd_to_jsonschema,
    get_source_by_name,
    load_sources,
    parse_crds_from_files,
    write_schema,
)

# Import extraction functions from extract.py
from extract import extract_github_crds, extract_helm_crds


def get_helm_versions(registry: str, chart: str, min_version: str | None = None) -> list[str]:
    """Get all available versions for a Helm chart."""
    versions = []

    if registry.startswith("oci://"):
        # OCI registry - use helm show to get versions
        # This is tricky as OCI doesn't have a standard version listing API
        # We'll use skopeo or crane if available, otherwise fall back to known versions
        try:
            # Try using crane to list tags
            result = subprocess.run(
                ["crane", "ls", registry.replace("oci://", "") + "/" + chart],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                versions = [v.strip() for v in result.stdout.strip().split("\n") if v.strip()]
        except FileNotFoundError:
            print(f"  Warning: crane not found, cannot list OCI versions for {chart}")
            return []
    else:
        # HTTP registry - use helm search or index.yaml
        try:
            # Fetch the index.yaml
            index_url = f"{registry.rstrip('/')}/index.yaml"
            response = requests.get(index_url, timeout=30)
            response.raise_for_status()

            index = yaml.safe_load(response.text)
            entries = index.get("entries", {}).get(chart, [])

            for entry in entries:
                version = entry.get("version")
                if version:
                    versions.append(version)

        except Exception as e:
            print(f"  Error fetching Helm index: {e}")
            return []

    # Filter by minimum version if specified
    if min_version and versions:
        versions = filter_versions(versions, min_version)

    # Sort versions (newest first)
    versions = sorted(versions, key=version_key, reverse=True)

    return versions


def get_github_versions(repo: str, min_version: str | None = None) -> list[str]:
    """Get all available releases for a GitHub repo."""
    versions = []

    try:
        # Use GitHub API to list releases
        url = f"https://api.github.com/repos/{repo}/releases"
        headers = {}

        # Use token if available
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"

        page = 1
        while True:
            response = requests.get(f"{url}?page={page}&per_page=100", headers=headers, timeout=30)
            response.raise_for_status()

            releases = response.json()
            if not releases:
                break

            for release in releases:
                tag = release.get("tag_name", "")
                if tag:
                    versions.append(tag)

            page += 1

            # Safety limit
            if page > 20:
                break

    except Exception as e:
        print(f"  Error fetching GitHub releases: {e}")
        return []

    # Filter by minimum version if specified
    if min_version and versions:
        versions = filter_versions(versions, min_version)

    # Sort versions (newest first)
    versions = sorted(versions, key=version_key, reverse=True)

    return versions


def version_key(version: str) -> tuple:
    """Create a sortable key from a version string."""
    # Remove common prefixes
    v = version.removeprefix("v").removeprefix("release-")

    # Split into parts
    parts = re.split(r"[.\-]", v)

    result = []
    for part in parts:
        # Try to convert to int for numeric comparison
        try:
            result.append((0, int(part)))
        except ValueError:
            # Handle alpha/beta/rc
            if "alpha" in part.lower():
                result.append((1, part))
            elif "beta" in part.lower():
                result.append((2, part))
            elif "rc" in part.lower():
                result.append((3, part))
            else:
                result.append((4, part))

    return tuple(result)


def filter_versions(versions: list[str], min_version: str) -> list[str]:
    """Filter versions to only include those >= min_version."""
    min_key = version_key(min_version)
    return [v for v in versions if version_key(v) >= min_key]


def extract_version(source: dict, version: str, output_dir: Path) -> int:
    """Extract schemas for a specific version of a source."""
    # Create a copy of source with the specific version
    source_copy = source.copy()
    source_copy["version"] = version

    source_type = source_copy["type"]
    name = source_copy["name"]

    print(f"  Extracting {name} {version}...")

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        try:
            # Extract CRD files based on source type
            if source_type == "helm":
                crd_files = extract_helm_crds(source_copy, work_dir)
            elif source_type == "github":
                crd_files = extract_github_crds(source_copy, work_dir)
            else:
                print(f"    Unknown source type: {source_type}")
                return 0

            if not crd_files:
                print("    No CRD files found")
                return 0

            # Parse CRDs
            crds = parse_crds_from_files(crd_files)
            if not crds:
                print("    No CRDs parsed")
                return 0

            # Convert to JSON schemas with provenance tracking
            schema_count = 0
            for crd in crds:
                schemas = crd_to_jsonschema(crd, name, version)
                for group, api_version, kind, schema in schemas:
                    write_schema(output_dir, group, api_version, kind, schema)
                    schema_count += 1

            return schema_count

        except Exception as e:
            print(f"    Error: {e}")
            return 0


def backfill_source(
    source: dict, output_dir: Path, min_version: str | None = None, max_versions: int | None = None
) -> dict:
    """Backfill all versions for a source. Returns stats."""
    name = source["name"]
    source_type = source["type"]

    print(f"\nBackfilling: {name}")

    # Discover all versions
    if source_type == "helm":
        versions = get_helm_versions(source["registry"], source["chart"], min_version)
    elif source_type == "github":
        versions = get_github_versions(source["repo"], min_version)
    else:
        print(f"  Unsupported source type: {source_type}")
        return {"name": name, "versions_found": 0, "versions_processed": 0, "schemas_extracted": 0}

    print(f"  Found {len(versions)} versions")

    if not versions:
        return {"name": name, "versions_found": 0, "versions_processed": 0, "schemas_extracted": 0}

    # Limit versions if specified
    if max_versions:
        versions = versions[:max_versions]
        print(f"  Processing {len(versions)} versions (limited)")

    # Extract each version
    total_schemas = 0
    processed = 0

    for version in versions:
        schemas = extract_version(source, version, output_dir)
        total_schemas += schemas
        processed += 1

    return {
        "name": name,
        "versions_found": len(versions),
        "versions_processed": processed,
        "schemas_extracted": total_schemas,
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill historical versions for CRD sources")
    parser.add_argument("--source", help="Specific source to backfill")
    parser.add_argument("--all", action="store_true", help="Backfill all sources")
    parser.add_argument("--output", default="schemas", help="Output directory")
    parser.add_argument("--sources-file", default="sources.yaml", help="Sources config file")
    parser.add_argument("--min-version", help="Minimum version to include")
    parser.add_argument("--max-versions", type=int, help="Maximum versions to process per source")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers (use with caution)")

    args = parser.parse_args()

    if not args.source and not args.all:
        parser.error("Either --source or --all must be specified")

    sources_config = load_sources(args.sources_file)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    if args.all:
        sources_to_process = sources_config.get("sources", [])
    else:
        source = get_source_by_name(sources_config, args.source)
        if not source:
            print(f"Source not found: {args.source}")
            sys.exit(1)
        sources_to_process = [source]

    print(f"Backfilling {len(sources_to_process)} sources...")

    if args.parallel > 1:
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(backfill_source, source, output_dir, args.min_version, args.max_versions): source
                for source in sources_to_process
            }
            for future in as_completed(futures):
                results.append(future.result())
    else:
        for source in sources_to_process:
            results.append(backfill_source(source, output_dir, args.min_version, args.max_versions))

    # Summary
    print("\n" + "=" * 60)
    print("BACKFILL SUMMARY")
    print("=" * 60)

    total_versions = sum(r["versions_found"] for r in results)
    total_processed = sum(r["versions_processed"] for r in results)
    total_schemas = sum(r["schemas_extracted"] for r in results)

    for r in results:
        print(
            f"  {r['name']}: {r['versions_processed']}/{r['versions_found']} versions, {r['schemas_extracted']} schemas"
        )

    print(f"\nTotal: {total_processed}/{total_versions} versions, {total_schemas} schemas")


if __name__ == "__main__":
    main()
