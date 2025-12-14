#!/usr/bin/env python3
"""
CRD Schema Extractor

Extracts CRDs from various sources (Helm charts, GitHub releases, URLs)
and converts them to JSON schemas for IDE validation.

Sources are organized in directories:
- sources/helm/{name}/helmrelease.yaml
- sources/kustomize/{name}/kustomization.yaml
- sources/github/{name}/source.yaml
- sources/url/{name}/source.yaml

Usage:
    python extract.py --source flux --output schemas/
    python extract.py --all --output schemas/
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

import requests
import yaml
from common import (
    SafeLoaderWithTags,
    crd_to_jsonschema,
    parse_crds_from_files,
    write_schema,
)


def load_sources(sources_dir: Path) -> list[dict]:
    """Load all sources from the directory structure."""
    sources = []

    # Load Helm sources
    helm_dir = sources_dir / "helm"
    if helm_dir.exists():
        for source_dir in sorted(helm_dir.iterdir()):
            if not source_dir.is_dir():
                continue
            helmrelease = source_dir / "helmrelease.yaml"
            if helmrelease.exists():
                with open(helmrelease) as f:
                    data = yaml.safe_load(f)
                sources.append({
                    "name": source_dir.name,
                    "type": "helm",
                    "registry": data["repository"],
                    "chart": data["chart"],
                    "version": str(data["version"]),
                    "values": data.get("values", {}),
                })

    # Load Kustomize sources (GitHub with crd_path)
    kustomize_dir = sources_dir / "kustomize"
    if kustomize_dir.exists():
        for source_dir in sorted(kustomize_dir.iterdir()):
            if not source_dir.is_dir():
                continue
            kustomization = source_dir / "kustomization.yaml"
            if kustomization.exists():
                with open(kustomization) as f:
                    data = yaml.safe_load(f)
                # Parse the resource URL
                # Format: https://github.com/owner/repo//path?ref=version
                resource = data.get("resources", [None])[0]
                if resource:
                    match = re.match(
                        r"https://github\.com/([^/]+/[^/]+)//(.+)\?ref=(.+)",
                        resource
                    )
                    if match:
                        sources.append({
                            "name": source_dir.name,
                            "type": "github",
                            "repo": match.group(1),
                            "crd_path": match.group(2),
                            "version": match.group(3),
                        })

    # Load GitHub sources (with assets)
    github_dir = sources_dir / "github"
    if github_dir.exists():
        for source_dir in sorted(github_dir.iterdir()):
            if not source_dir.is_dir():
                continue
            source_file = source_dir / "source.yaml"
            if source_file.exists():
                with open(source_file) as f:
                    data = yaml.safe_load(f)
                sources.append({
                    "name": source_dir.name,
                    "type": "github",
                    "repo": data["repository"],
                    "version": str(data["version"]),
                    "assets": data.get("assets", []),
                })

    # Load URL sources
    url_dir = sources_dir / "url"
    if url_dir.exists():
        for source_dir in sorted(url_dir.iterdir()):
            if not source_dir.is_dir():
                continue
            source_file = source_dir / "source.yaml"
            if source_file.exists():
                with open(source_file) as f:
                    data = yaml.safe_load(f)
                sources.append({
                    "name": source_dir.name,
                    "type": "url",
                    "url": data["url"],
                    "version": str(data["version"]),
                })

    return sources


def get_source_by_name(sources: list[dict], name: str) -> dict | None:
    """Find a source by name."""
    for source in sources:
        if source["name"] == name:
            return source
    return None


def extract_helm_crds(source: dict, work_dir: Path) -> list[Path]:
    """Extract CRDs from a Helm chart using helm template."""
    import subprocess

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
        values_file.write_text(yaml.dump(values))
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
    crd_docs = []
    try:
        for doc in yaml.load_all(rendered, Loader=SafeLoaderWithTags):
            if doc and doc.get("kind") == "CustomResourceDefinition":
                crd_docs.append(doc)
    except yaml.YAMLError as e:
        print(f"  Error parsing helm template output: {e}")
        return []

    if not crd_docs:
        print("  No CRDs found in rendered output")
        return []

    # Write CRDs to a single file
    crd_file = work_dir / "crds.yaml"
    with open(crd_file, "w") as f:
        yaml.dump_all(crd_docs, f)

    print(f"  Found {len(crd_docs)} CRDs")
    return [crd_file]


def extract_github_crds(source: dict, work_dir: Path) -> list[Path]:
    """Extract CRDs from GitHub release assets or directories."""
    import os

    repo = source["repo"]
    version = source["version"]
    assets = source.get("assets", [])
    crd_path = source.get("crd_path")

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
    """Recursively discover all YAML files in a GitHub directory."""
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
    parser.add_argument("--sources-dir", default="sources", help="Sources directory")

    args = parser.parse_args()

    if not args.source and not args.all:
        parser.error("Either --source or --all must be specified")

    sources_dir = Path(args.sources_dir)
    if not sources_dir.exists():
        print(f"Sources directory not found: {sources_dir}")
        sys.exit(1)

    sources = load_sources(sources_dir)
    print(f"Loaded {len(sources)} sources")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_schemas = 0

    if args.all:
        for source in sources:
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
