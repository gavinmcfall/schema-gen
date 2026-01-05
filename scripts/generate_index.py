#!/usr/bin/env python3
"""
Generate a JSON index of all schemas for the web interface.

This creates a schemas-index.json file that the web UI loads to display
available schemas without embedding them in HTML.
"""

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common import parse_schema_path

logger = logging.getLogger(__name__)


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
        parsed = parse_schema_path(schema_file, schemas_dir)
        if not parsed:
            continue

        group, version, kind = parsed

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
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    index = generate_index(args.schemas_dir)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(index, f, indent=2)

    logger.info(
        "Generated index: %d schemas in %d groups", index["stats"]["totalSchemas"], index["stats"]["totalGroups"]
    )
    logger.info("Output: %s", output_path)


if __name__ == "__main__":
    main()
