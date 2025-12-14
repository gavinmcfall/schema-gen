#!/usr/bin/env python3
"""
Migrate sources.yaml to directory-based structure.

This creates:
- sources/helm/{name}/helmrelease.yaml
- sources/kustomize/{name}/kustomization.yaml  (for github with crd_path)
- sources/github/{name}/source.yaml  (for github with assets)
- sources/url/{name}/source.yaml

Each format is designed for native Renovate manager support.
"""

import re
from pathlib import Path

import yaml


def migrate_helm_source(source: dict, output_dir: Path) -> None:
    """Migrate a Helm source to helmrelease.yaml format."""
    name = source["name"]
    target_dir = output_dir / "helm" / name
    target_dir.mkdir(parents=True, exist_ok=True)

    # Build helmrelease.yaml content
    content = {
        "repository": source["registry"],
        "chart": source["chart"],
        "version": source["version"],
    }

    if "values" in source:
        content["values"] = source["values"]

    target_file = target_dir / "helmrelease.yaml"
    with open(target_file, "w") as f:
        yaml.dump(content, f, default_flow_style=False, sort_keys=False)

    print(f"  Created: {target_file}")


def migrate_github_kustomize_source(source: dict, output_dir: Path) -> None:
    """Migrate a GitHub source with crd_path to kustomization.yaml format."""
    name = source["name"]
    target_dir = output_dir / "kustomize" / name
    target_dir.mkdir(parents=True, exist_ok=True)

    repo = source["repo"]
    version = source["version"]
    crd_path = source["crd_path"]

    # Build kustomization with remote resource
    # Format: https://github.com/owner/repo//path?ref=version
    resource_url = f"https://github.com/{repo}//{crd_path}?ref={version}"

    content = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": [resource_url],
    }

    target_file = target_dir / "kustomization.yaml"
    with open(target_file, "w") as f:
        yaml.dump(content, f, default_flow_style=False, sort_keys=False)

    print(f"  Created: {target_file}")


def migrate_github_assets_source(source: dict, output_dir: Path) -> None:
    """Migrate a GitHub source with assets to source.yaml format."""
    name = source["name"]
    target_dir = output_dir / "github" / name
    target_dir.mkdir(parents=True, exist_ok=True)

    repo = source["repo"]
    version = source["version"]
    assets = source.get("assets", [])

    # Write with renovate hint comment
    target_file = target_dir / "source.yaml"
    with open(target_file, "w") as f:
        f.write(f"# renovate: datasource=github-releases depName={repo}\n")
        content = {
            "repository": repo,
            "version": version,
            "assets": assets,
        }
        yaml.dump(content, f, default_flow_style=False, sort_keys=False)

    print(f"  Created: {target_file}")


def migrate_url_source(source: dict, output_dir: Path) -> None:
    """Migrate a URL source to source.yaml format."""
    name = source["name"]
    target_dir = output_dir / "url" / name
    target_dir.mkdir(parents=True, exist_ok=True)

    url = source["url"]
    version = source["version"]

    # Try to extract GitHub repo from URL for renovate hint
    github_match = re.match(r"https://github\.com/([^/]+/[^/]+)/", url)

    target_file = target_dir / "source.yaml"
    with open(target_file, "w") as f:
        if github_match:
            repo = github_match.group(1)
            f.write(f"# renovate: datasource=github-releases depName={repo}\n")
        content = {
            "url": url,
            "version": version,
        }
        yaml.dump(content, f, default_flow_style=False, sort_keys=False)

    print(f"  Created: {target_file}")


def main():
    sources_file = Path("sources.yaml")
    output_dir = Path("sources")

    if not sources_file.exists():
        print(f"Error: {sources_file} not found")
        return

    with open(sources_file) as f:
        data = yaml.safe_load(f)

    sources = data.get("sources", [])
    print(f"Migrating {len(sources)} sources...")

    helm_count = 0
    kustomize_count = 0
    github_count = 0
    url_count = 0
    skipped = []

    for source in sources:
        name = source.get("name", "unknown")
        source_type = source.get("type")

        if source_type == "helm":
            migrate_helm_source(source, output_dir)
            helm_count += 1
        elif source_type == "github":
            if "crd_path" in source:
                migrate_github_kustomize_source(source, output_dir)
                kustomize_count += 1
            elif "assets" in source:
                migrate_github_assets_source(source, output_dir)
                github_count += 1
            else:
                skipped.append(f"{name} (github without crd_path or assets)")
        elif source_type == "url":
            migrate_url_source(source, output_dir)
            url_count += 1
        else:
            skipped.append(f"{name} (unknown type: {source_type})")

    print("\nMigration complete:")
    print(f"  Helm sources:      {helm_count}")
    print(f"  Kustomize sources: {kustomize_count}")
    print(f"  GitHub sources:    {github_count}")
    print(f"  URL sources:       {url_count}")

    if skipped:
        print(f"\nSkipped ({len(skipped)}):")
        for s in skipped:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
