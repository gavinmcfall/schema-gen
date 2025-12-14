#!/usr/bin/env python3
"""
CRD Schema Extractor

Extracts CRDs from various sources (Helm charts, GitHub releases, URLs)
and converts them to JSON schemas for IDE validation.

Usage:
    python extract.py --source flux --output schemas/
    python extract.py --all --output schemas/
"""

import argparse
import sys
import tempfile
from pathlib import Path

import requests
from common import (
    SafeLoaderWithTags,
    crd_to_jsonschema,
    get_source_by_name,
    load_sources,
    parse_crds_from_files,
    run_command,
    write_schema,
)


def extract_helm_crds(source: dict, work_dir: Path) -> list[Path]:
    """Extract CRDs from a Helm chart using helm template.

    This renders the chart with helm template and filters for CRDs,
    which handles charts that have CRDs in templates/ as Helm templates.
    """
    import subprocess

    import yaml as pyyaml

    registry = source["registry"]
    chart = source["chart"]
    version = source["version"]
    values = source.get("values", {})

    # Build chart reference
    if registry.startswith("oci://"):
        chart_ref = f"{registry}/{chart}"
    else:
        chart_ref = chart

    # Build helm template command
    cmd = ["helm", "template", "release", chart_ref, "--version", version, "--include-crds"]

    # Add repo for HTTP registries
    if not registry.startswith("oci://"):
        cmd.extend(["--repo", registry])

    # Add values if specified
    if values:
        values_file = work_dir / "values.yaml"
        values_file.write_text(pyyaml.dump(values))
        cmd.extend(["--values", str(values_file)])

    print(f"  Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  Error running helm template: {result.stderr}")
        return []

    rendered = result.stdout

    if not rendered.strip():
        print("  No output from helm template")
        return []

    # Parse the rendered output and filter for CRDs
    # Use SafeLoaderWithTags to handle special YAML tags like tag:yaml.org,2002:value
    crd_docs = []
    try:
        for doc in pyyaml.load_all(rendered, Loader=SafeLoaderWithTags):
            if doc and doc.get("kind") == "CustomResourceDefinition":
                crd_docs.append(doc)
    except pyyaml.YAMLError as e:
        print(f"  Error parsing helm template output: {e}")
        return []

    if not crd_docs:
        print("  No CRDs found in rendered output")
        return []

    # Write CRDs to a single file
    crd_file = work_dir / "crds.yaml"
    with open(crd_file, "w") as f:
        pyyaml.dump_all(crd_docs, f)

    print(f"  Found {len(crd_docs)} CRDs")
    return [crd_file]


def extract_github_crds(source: dict, work_dir: Path) -> list[Path]:
    """Extract CRDs from GitHub release assets or directories."""
    import os

    repo = source["repo"]
    version = source["version"]
    assets = source.get("assets", [])
    crd_path = source.get("crd_path")  # Directory to discover CRDs from

    crd_files = []

    # Build headers for GitHub API
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    # If crd_path is specified, discover all YAML files in that directory
    if crd_path:
        print(f"  Discovering CRDs in {crd_path}...")
        discovered = discover_github_yaml_files(repo, version, crd_path, headers)
        assets = assets + discovered
        print(f"  Found {len(discovered)} CRD files")

    for asset in assets:
        # Handle both direct filenames and paths
        if "/" in asset:
            # Path within the repo
            url = f"https://raw.githubusercontent.com/{repo}/{version}/{asset}"
        else:
            # Release asset
            url = f"https://github.com/{repo}/releases/download/{version}/{asset}"

        print(f"  Fetching: {url}")

        try:
            response = requests.get(url, timeout=30, headers=headers)
            response.raise_for_status()

            # Save to work directory
            filename = asset.replace("/", "_")
            filepath = work_dir / filename
            filepath.write_text(response.text)
            crd_files.append(filepath)

        except requests.RequestException as e:
            print(f"  Error fetching {asset}: {e}")

    return crd_files


def discover_github_yaml_files(repo: str, version: str, path: str, headers: dict) -> list[str]:
    """
    Recursively discover all YAML files in a GitHub directory.

    Uses GitHub API to list directory contents and find all .yaml/.yml files.
    """
    yaml_files = []
    path = path.rstrip("/")

    api_url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={version}"

    try:
        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()
        contents = response.json()

        for item in contents:
            if item["type"] == "file" and (item["name"].endswith(".yaml") or item["name"].endswith(".yml")):
                yaml_files.append(item["path"])
            elif item["type"] == "dir":
                # Recursively scan subdirectories
                yaml_files.extend(discover_github_yaml_files(repo, version, item["path"], headers))

    except requests.RequestException as e:
        print(f"  Error listing {path}: {e}")

    return yaml_files


def extract_url_crds(source: dict, work_dir: Path) -> list[Path]:
    """Extract CRDs from direct URLs."""
    url = source["url"]
    version = source["version"]

    # Replace {version} placeholder
    url = url.replace("{version}", version)

    print(f"  Fetching: {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        filepath = work_dir / "crd.yaml"
        filepath.write_text(response.text)
        return [filepath]

    except requests.RequestException as e:
        print(f"  Error fetching URL: {e}")
        return []


def extract_source(source: dict, output_dir: Path) -> int:
    """Extract schemas from a single source. Returns number of schemas extracted."""
    name = source["name"]
    source_type = source["type"]

    print(f"\nExtracting: {name} (type: {source_type})")

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        # Extract CRD files based on source type
        if source_type == "helm":
            crd_files = extract_helm_crds(source, work_dir)
        elif source_type == "github":
            crd_files = extract_github_crds(source, work_dir)
        elif source_type == "url":
            crd_files = extract_url_crds(source, work_dir)
        else:
            print(f"  Unknown source type: {source_type}")
            return 0

        if not crd_files:
            print("  No CRD files found")
            return 0

        # Parse CRDs
        crds = parse_crds_from_files(crd_files)
        print(f"  Found {len(crds)} CRD definitions")

        # Get source metadata for provenance tracking
        source_name = source["name"]
        source_version = source.get("version", "unknown")

        # Convert to JSON schemas
        schema_count = 0
        for crd in crds:
            schemas = crd_to_jsonschema(crd, source_name, source_version)
            for group, version, kind, schema in schemas:
                write_schema(output_dir, group, version, kind, schema)
                schema_count += 1

        return schema_count


def main():
    parser = argparse.ArgumentParser(description="Extract CRD schemas")
    parser.add_argument("--source", help="Specific source to extract")
    parser.add_argument("--all", action="store_true", help="Extract all sources")
    parser.add_argument("--output", default="schemas", help="Output directory")
    parser.add_argument("--sources-file", default="sources.yaml", help="Sources config file")

    args = parser.parse_args()

    if not args.source and not args.all:
        parser.error("Either --source or --all must be specified")

    sources = load_sources(args.sources_file)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_schemas = 0

    if args.all:
        for source in sources.get("sources", []):
            total_schemas += extract_source(source, output_dir)
    else:
        source = get_source_by_name(sources, args.source)
        if not source:
            print(f"Source not found: {args.source}")
            sys.exit(1)
        total_schemas = extract_source(source, output_dir)

    print(f"\nTotal schemas extracted: {total_schemas}")


if __name__ == "__main__":
    main()
