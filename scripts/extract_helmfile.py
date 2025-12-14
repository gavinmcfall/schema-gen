#!/usr/bin/env python3
"""
Extract CRDs using helmfile template approach.

This uses helmfile's ability to render charts with --include-crds and then
filter to only CRD resources using yq. This is more reliable than parsing
chart directories directly.

Requires: helmfile, helm, yq

Usage:
    python extract_helmfile.py --source cert-manager --output schemas/
    python extract_helmfile.py --generate-helmfile  # Generate helmfile from sources.yaml
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from common import (
    crd_to_jsonschema,
    get_source_by_name,
    load_sources,
    parse_crds_from_files,
    write_schema,
)

HELMFILE_TEMPLATE = """---
# Auto-generated helmfile for CRD extraction
# yaml-language-server: $schema=https://json.schemastore.org/helmfile

helmDefaults:
  args:
    - --include-crds
    - --no-hooks
  postRenderer: bash
  postRendererArgs:
    - -c
    - yq ea -e 'select(.kind == "CustomResourceDefinition")'

releases:
{releases}
"""

RELEASE_TEMPLATE = """  - name: {name}
    namespace: default
    chart: {chart_ref}
    version: {version}
"""


def check_dependencies():
    """Check that required tools are installed."""
    tools = ["helmfile", "helm", "yq"]
    missing = []

    for tool in tools:
        result = subprocess.run(["which", tool], capture_output=True)
        if result.returncode != 0:
            missing.append(tool)

    if missing:
        print(f"Error: Missing required tools: {', '.join(missing)}")
        print("Install with:")
        print("  brew install helmfile helm yq  # macOS")
        print("  # or see respective installation docs")
        sys.exit(1)


def generate_helmfile(sources_config: dict, output_path: Path):
    """Generate a helmfile from sources.yaml for CRD extraction."""
    releases = []

    for source in sources_config.get("sources", []):
        if source["type"] != "helm":
            continue

        registry = source["registry"]
        chart = source["chart"]
        version = source["version"]
        name = source["name"]

        # Build chart reference
        if registry.startswith("oci://"):
            chart_ref = f"{registry}/{chart}"
        else:
            chart_ref = f"{registry}/{chart}"

        releases.append(
            RELEASE_TEMPLATE.format(
                name=name,
                chart_ref=chart_ref,
                version=version,
            )
        )

    helmfile_content = HELMFILE_TEMPLATE.format(releases="".join(releases))

    output_path.write_text(helmfile_content)
    print(f"Generated helmfile at: {output_path}")
    print(f"  Contains {len(releases)} Helm releases")


def extract_with_helmfile(source: dict, output_dir: Path) -> int:
    """Extract CRDs from a single source using helmfile template."""
    name = source["name"]
    registry = source["registry"]
    chart = source["chart"]
    version = source["version"]
    values = source.get("values", {})

    print(f"\nExtracting: {name} v{version}")
    if values:
        print("  Using custom values to enable all CRDs")

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        # Write values file if we have custom values
        values_section = ""
        if values:
            values_file = work_dir / "values.yaml"
            values_file.write_text(yaml.dump(values))
            values_section = """
    values:
      - values.yaml"""

        # Build chart reference and repository section
        if registry.startswith("oci://"):
            chart_ref = f"{registry}/{chart}"
            repo_section = ""
        else:
            # HTTP registry - need to define repository
            chart_ref = f"repo/{chart}"
            repo_section = f"""
repositories:
  - name: repo
    url: {registry}
"""

        # Create minimal helmfile
        helmfile_content = f"""---
helmDefaults:
  args:
    - --include-crds
    - --no-hooks
{repo_section}
releases:
  - name: {name}
    namespace: default
    chart: {chart_ref}
    version: {version}{values_section}
"""
        helmfile_path = work_dir / "helmfile.yaml"
        helmfile_path.write_text(helmfile_content)

        # Run helmfile template
        print("  Running helmfile template...")
        result = subprocess.run(
            ["helmfile", "template", "--file", str(helmfile_path)],
            capture_output=True,
            text=True,
            cwd=work_dir,
        )

        if result.returncode != 0:
            print(f"  Error running helmfile: {result.stderr}")
            return 0

        rendered = result.stdout

        # Filter to only CRDs using yq
        print("  Filtering CRDs...")
        yq_result = subprocess.run(
            ["yq", "ea", "-e", 'select(.kind == "CustomResourceDefinition")'],
            input=rendered,
            capture_output=True,
            text=True,
        )

        if yq_result.returncode != 0:
            # No CRDs found is not necessarily an error
            if "no matches found" in yq_result.stderr.lower() or not yq_result.stderr:
                print("  No CRDs found in chart")
                return 0
            print(f"  Error filtering CRDs: {yq_result.stderr}")
            return 0

        crd_yaml = yq_result.stdout

        if not crd_yaml.strip():
            print("  No CRDs found in chart")
            return 0

        # Write CRDs to temp file and parse
        crd_file = work_dir / "crds.yaml"
        crd_file.write_text(crd_yaml)

        # Parse and convert
        crds = parse_crds_from_files([crd_file])
        print(f"  Found {len(crds)} CRD definitions")

        # Get source metadata for provenance tracking
        source_name = source["name"]
        source_version = source.get("version", "unknown")

        schema_count = 0
        for crd in crds:
            schemas = crd_to_jsonschema(crd, source_name, source_version)
            for group, api_version, kind, schema in schemas:
                write_schema(output_dir, group, api_version, kind, schema)
                schema_count += 1

        return schema_count


def extract_all_helm_sources(sources_config: dict, output_dir: Path) -> int:
    """Extract CRDs from all Helm sources."""
    total = 0

    for source in sources_config.get("sources", []):
        if source["type"] != "helm":
            continue

        count = extract_with_helmfile(source, output_dir)
        total += count

    return total


def main():
    parser = argparse.ArgumentParser(description="Extract CRDs using helmfile")
    parser.add_argument("--source", help="Specific source to extract")
    parser.add_argument("--all", action="store_true", help="Extract all Helm sources")
    parser.add_argument("--output", default="schemas", help="Output directory")
    parser.add_argument("--sources-file", default="sources.yaml", help="Sources config file")
    parser.add_argument("--generate-helmfile", metavar="PATH", help="Generate helmfile.yaml for all sources")

    args = parser.parse_args()

    check_dependencies()

    sources_config = load_sources(args.sources_file)

    if args.generate_helmfile:
        generate_helmfile(sources_config, Path(args.generate_helmfile))
        return

    if not args.source and not args.all:
        parser.error("Either --source, --all, or --generate-helmfile must be specified")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        total = extract_all_helm_sources(sources_config, output_dir)
    else:
        source = get_source_by_name(sources_config, args.source)
        if not source:
            print(f"Source not found: {args.source}")
            sys.exit(1)
        if source["type"] != "helm":
            print(f"Source {args.source} is not a Helm source (type: {source['type']})")
            sys.exit(1)
        total = extract_with_helmfile(source, output_dir)

    print(f"\nTotal schemas extracted: {total}")


if __name__ == "__main__":
    main()
