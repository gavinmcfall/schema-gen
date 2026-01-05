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
import logging
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
from common import (
    crd_to_jsonschema,
    get_http_session,
    parse_crds_from_files,
    write_schema,
)

# Import extraction functions from extract.py
from extract import extract_github_crds, extract_helm_crds, get_source_by_name, load_sources
from requests import RequestException

logger = logging.getLogger(__name__)


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
                timeout=60,
            )
            if result.returncode == 0:
                versions = [v.strip() for v in result.stdout.strip().split("\n") if v.strip()]
        except FileNotFoundError:
            logger.warning("crane not found, cannot list OCI versions for %s", chart)
            return []
    else:
        # HTTP registry - use helm search or index.yaml
        try:
            session = get_http_session()
            # Fetch the index.yaml
            index_url = f"{registry.rstrip('/')}/index.yaml"
            response = session.get(index_url, timeout=60)
            response.raise_for_status()

            index = yaml.safe_load(response.text)
            entries = index.get("entries", {}).get(chart, [])

            for entry in entries:
                version = entry.get("version")
                if version:
                    versions.append(version)

        except RequestException as e:
            logger.error("Error fetching Helm index: %s", e)
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
    session = get_http_session()

    try:
        # Use GitHub API to list releases
        url = f"https://api.github.com/repos/{repo}/releases"

        page = 1
        while True:
            response = session.get(f"{url}?page={page}&per_page=100", timeout=60)
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

    except RequestException as e:
        logger.error("Error fetching GitHub releases: %s", e)
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

    logger.debug("Extracting %s %s...", name, version)

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        try:
            # Extract CRD files based on source type
            if source_type == "helm":
                crd_files = extract_helm_crds(source_copy, work_dir)
            elif source_type == "github":
                crd_files = extract_github_crds(source_copy, work_dir)
            else:
                logger.error("Unknown source type: %s", source_type)
                return 0

            if not crd_files:
                logger.debug("No CRD files found")
                return 0

            # Parse CRDs
            crds = parse_crds_from_files(crd_files)
            if not crds:
                logger.debug("No CRDs parsed")
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
            logger.error("Error extracting %s %s: %s", name, version, e)
            return 0


def backfill_source(
    source: dict, output_dir: Path, min_version: str | None = None, max_versions: int | None = None
) -> dict:
    """Backfill all versions for a source. Returns stats."""
    name = source["name"]
    source_type = source["type"]

    logger.info("Backfilling: %s", name)

    # Discover all versions
    if source_type == "helm":
        versions = get_helm_versions(source["registry"], source["chart"], min_version)
    elif source_type == "github":
        versions = get_github_versions(source["repo"], min_version)
    else:
        logger.error("Unsupported source type: %s", source_type)
        return {"name": name, "versions_found": 0, "versions_processed": 0, "schemas_extracted": 0}

    logger.debug("Found %d versions", len(versions))

    if not versions:
        return {"name": name, "versions_found": 0, "versions_processed": 0, "schemas_extracted": 0}

    # Limit versions if specified
    if max_versions:
        versions = versions[:max_versions]
        logger.debug("Processing %d versions (limited)", len(versions))

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
    parser.add_argument("--sources-dir", default="sources", help="Sources directory")
    parser.add_argument("--min-version", help="Minimum version to include")
    parser.add_argument("--max-versions", type=int, help="Maximum versions to process per source")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers (use with caution)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not args.source and not args.all:
        parser.error("Either --source or --all must be specified")

    sources_dir = Path(args.sources_dir)
    if not sources_dir.exists():
        logger.error("Sources directory not found: %s", sources_dir)
        sys.exit(1)

    sources = load_sources(sources_dir)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    if args.all:
        sources_to_process = sources
    else:
        source = get_source_by_name(sources, args.source)
        if not source:
            logger.error("Source not found: %s", args.source)
            sys.exit(1)
        sources_to_process = [source]

    logger.info("Backfilling %d sources...", len(sources_to_process))

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
    logger.info("=" * 60)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 60)

    total_versions = sum(r["versions_found"] for r in results)
    total_processed = sum(r["versions_processed"] for r in results)
    total_schemas = sum(r["schemas_extracted"] for r in results)
    failed_sources = [r["name"] for r in results if r["schemas_extracted"] == 0 and r["versions_found"] > 0]

    for r in results:
        logger.info(
            "  %s: %d/%d versions, %d schemas",
            r["name"],
            r["versions_processed"],
            r["versions_found"],
            r["schemas_extracted"],
        )

    logger.info("Total: %d/%d versions, %d schemas", total_processed, total_versions, total_schemas)

    if failed_sources:
        logger.error("Failed sources (%d): %s", len(failed_sources), ", ".join(failed_sources))
        sys.exit(1)


if __name__ == "__main__":
    main()
