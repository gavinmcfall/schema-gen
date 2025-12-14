#!/usr/bin/env python3
"""
Generate a JSON index of all schemas for the web interface.

This creates a schemas-index.json file that the web UI loads to display
available schemas without embedding them in HTML.
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def generate_index(schemas_dir: Path) -> dict:
    """Generate a schema index from the schemas directory."""
    schemas_dir = Path(schemas_dir)

    # Structure: { group: { version: [kinds] } }
    groups = defaultdict(lambda: defaultdict(list))

    # Track metadata
    total_schemas = 0
    sources = set()

    # Scan all JSON files
    for schema_file in schemas_dir.rglob("*.json"):
        # Skip non-schema files
        if schema_file.name in ("schemas-index.json", "sources.schema.json"):
            continue

        # Parse path: schemas/{group}/{version}/{kind}.json
        try:
            parts = schema_file.relative_to(schemas_dir).parts
            if len(parts) != 3:
                continue

            group, version, kind_file = parts
            kind = kind_file.replace(".json", "")

            # Try to extract source metadata from schema
            source_name = None
            source_version = None
            try:
                with open(schema_file) as f:
                    schema = json.load(f)
                    metadata = schema.get("x-kubernetes-schema-metadata", {})
                    source_name = metadata.get("sourceName")
                    source_version = metadata.get("sourceVersion")
                    if source_name:
                        sources.add(source_name)
            except (json.JSONDecodeError, IOError):
                pass

            groups[group][version].append(
                {
                    "kind": kind,
                    "source": source_name,
                    "sourceVersion": source_version,
                }
            )
            total_schemas += 1

        except ValueError:
            continue

    # Sort everything
    sorted_groups = {}
    for group in sorted(groups.keys()):
        sorted_groups[group] = {}
        for version in sorted(groups[group].keys(), reverse=True):
            sorted_groups[group][version] = sorted(groups[group][version], key=lambda x: x["kind"])

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "totalSchemas": total_schemas,
            "totalGroups": len(groups),
            "totalSources": len(sources),
        },
        "groups": sorted_groups,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate schema index")
    parser.add_argument("--schemas-dir", default="schemas", help="Directory containing schemas")
    parser.add_argument("--output", default="schemas/schemas-index.json", help="Output index file")

    args = parser.parse_args()

    index = generate_index(args.schemas_dir)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(index, f, indent=2)

    print(f"Generated index: {index['stats']['totalSchemas']} schemas in {index['stats']['totalGroups']} groups")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
