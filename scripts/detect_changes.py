#!/usr/bin/env python3
"""
Detect which sources changed between two git commits.

Usage:
    python detect_changes.py HEAD~1 HEAD
"""

import subprocess
import sys

import yaml


def get_file_at_commit(commit: str, filepath: str) -> str | None:
    """Get file contents at a specific commit."""
    result = subprocess.run(
        ["git", "show", f"{commit}:{filepath}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def main():
    if len(sys.argv) != 3:
        print("Usage: detect_changes.py <old_commit> <new_commit>", file=sys.stderr)
        sys.exit(1)

    old_commit = sys.argv[1]
    new_commit = sys.argv[2]

    # Get sources.yaml at both commits
    old_content = get_file_at_commit(old_commit, "sources.yaml")
    new_content = get_file_at_commit(new_commit, "sources.yaml")

    if new_content is None:
        print("", end="")
        sys.exit(0)

    new_sources = yaml.safe_load(new_content)

    # If old doesn't exist, all sources are new
    if old_content is None:
        sources = [s["name"] for s in new_sources.get("sources", [])]
        print(",".join(sources), end="")
        sys.exit(0)

    old_sources = yaml.safe_load(old_content)

    # Build lookup of old sources by name
    old_by_name = {s["name"]: s for s in old_sources.get("sources", [])}

    # Find changed/new sources
    changed = []
    for source in new_sources.get("sources", []):
        name = source["name"]
        if name not in old_by_name:
            # New source
            changed.append(name)
        elif source != old_by_name[name]:
            # Changed source (version bump, etc.)
            changed.append(name)

    print(",".join(changed), end="")


if __name__ == "__main__":
    main()
