#!/usr/bin/env python3
"""
Detect which sources changed between two git commits.

Works with the directory-based source structure:
- sources/helm/{name}/helmrelease.yaml
- sources/kustomize/{name}/kustomization.yaml
- sources/github/{name}/source.yaml
- sources/url/{name}/source.yaml

Usage:
    python detect_changes.py HEAD~1 HEAD
"""

import re
import subprocess
import sys
from pathlib import Path


def get_changed_files(old_commit: str, new_commit: str) -> list[str]:
    """Get list of files changed between two commits."""
    result = subprocess.run(
        ["git", "diff", "--name-only", old_commit, new_commit],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def extract_source_name(filepath: str) -> str | None:
    """Extract source name from a sources/ file path."""
    # Match patterns like:
    # sources/helm/flux/helmrelease.yaml -> flux
    # sources/kustomize/cilium/kustomization.yaml -> cilium
    # sources/github/gateway-api/source.yaml -> gateway-api
    # sources/url/hierarchical-namespaces/source.yaml -> hierarchical-namespaces

    match = re.match(r"sources/(helm|kustomize|github|url)/([^/]+)/", filepath)
    if match:
        return match.group(2)
    return None


def main():
    if len(sys.argv) != 3:
        print("Usage: detect_changes.py <old_commit> <new_commit>", file=sys.stderr)
        sys.exit(1)

    old_commit = sys.argv[1]
    new_commit = sys.argv[2]

    # Get changed files
    changed_files = get_changed_files(old_commit, new_commit)

    # Extract unique source names from changed files
    changed_sources = set()
    for filepath in changed_files:
        if filepath.startswith("sources/"):
            source_name = extract_source_name(filepath)
            if source_name:
                changed_sources.add(source_name)

    # Output comma-separated list
    print(",".join(sorted(changed_sources)), end="")


if __name__ == "__main__":
    main()
