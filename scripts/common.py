#!/usr/bin/env python3
"""
Common utilities for CRD schema extraction.

This module contains shared functionality used across all extraction scripts:
- Source configuration loading
- CRD parsing and schema conversion
- Schema I/O operations
- Utility functions
"""

import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# =============================================================================
# HTTP UTILITIES
# =============================================================================

# Module-level session for connection reuse
_http_session: requests.Session | None = None


def get_http_session() -> requests.Session:
    """
    Get a configured HTTP session with retry logic.

    Features:
    - Retries on 429, 500, 502, 503, 504 errors
    - Exponential backoff (0.5s, 1s, 2s)
    - Connection pooling for efficiency
    - GitHub token auth if GITHUB_TOKEN is set
    """
    global _http_session
    if _http_session is not None:
        return _http_session

    session = requests.Session()

    # Configure retry strategy
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Add GitHub token if available
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        session.headers["Authorization"] = f"token {token}"

    _http_session = session
    return session


def get_github_headers() -> dict:
    """Get headers for GitHub API requests."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


# =============================================================================
# SHELL UTILITIES
# =============================================================================


def run_command(cmd: list[str], cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


# =============================================================================
# CRD PARSING
# =============================================================================


class SafeLoaderWithTags(yaml.SafeLoader):
    """YAML loader that handles arbitrary tags by treating them as strings.

    Some CRDs (like kube-prometheus-stack) use special YAML tags like
    `tag:yaml.org,2002:value` that aren't handled by safe_load.
    """

    pass


# Add a constructor for any unknown tag - just return the value as-is
def _construct_undefined(self, node):
    if isinstance(node, yaml.ScalarNode):
        return self.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return self.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return self.construct_mapping(node)
    return None


SafeLoaderWithTags.add_constructor(None, _construct_undefined)


def parse_crds_from_files(crd_files: list[Path]) -> list[dict]:
    """Parse CRD definitions from YAML files."""
    crds = []

    for filepath in crd_files:
        try:
            content = filepath.read_text()

            # Handle multi-document YAML with custom loader for special tags
            for doc in yaml.load_all(content, Loader=SafeLoaderWithTags):
                if doc is None:
                    continue

                # Check if this is a CRD
                if doc.get("kind") == "CustomResourceDefinition":
                    crds.append(doc)

        except yaml.YAMLError as e:
            logger.error("Error parsing %s: %s", filepath, e)

    return crds


# =============================================================================
# SCHEMA CONVERSION
# =============================================================================


def crd_to_jsonschema(
    crd: dict,
    source_name: str | None = None,
    source_version: str | None = None,
) -> list[tuple[str, str, str, dict]]:
    """
    Convert a CRD to JSON Schema(s).

    Returns list of (group, version, kind, schema) tuples.
    """
    schemas = []

    spec = crd.get("spec", {})
    group = spec.get("group", "")
    kind = spec.get("names", {}).get("kind", "")

    if not group or not kind:
        return schemas

    # Handle both v1 and v1beta1 CRD formats
    versions = spec.get("versions", [])

    # v1beta1 format has schema at spec.validation.openAPIV3Schema
    if not versions and "validation" in spec:
        version = spec.get("version", "v1")
        openapi_schema = spec.get("validation", {}).get("openAPIV3Schema", {})
        if openapi_schema:
            schema = convert_openapi_to_jsonschema(openapi_schema, group, version, kind, source_name, source_version)
            schemas.append((group, version, kind.lower(), schema))
        return schemas

    # v1 format has schema per version
    for ver in versions:
        version_name = ver.get("name", "")
        openapi_schema = ver.get("schema", {}).get("openAPIV3Schema", {})

        if not openapi_schema:
            continue

        schema = convert_openapi_to_jsonschema(openapi_schema, group, version_name, kind, source_name, source_version)
        schemas.append((group, version_name, kind.lower(), schema))

    return schemas


def convert_openapi_to_jsonschema(
    openapi_schema: dict,
    group: str,
    version: str,
    kind: str,
    source_name: str | None = None,
    source_version: str | None = None,
) -> dict:
    """Convert OpenAPI v3 schema to JSON Schema."""
    # First, convert the entire OpenAPI schema to handle k8s extensions
    converted = deep_convert_schema(openapi_schema)

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://k8s-schemas.io/{group}/{version}/{kind.lower()}.json",
        "title": kind,
        "description": f"{kind} is the Schema for the {kind.lower()}s API",
        "type": "object",
    }

    # Add provenance metadata for historical tracking
    if source_name or source_version:
        schema["x-kubernetes-schema-metadata"] = {
            "sourceName": source_name,
            "sourceVersion": source_version,
            "extractedAt": datetime.now(timezone.utc).isoformat(),
            "generator": "k8s-schemas.io",
        }

    # Copy over the converted properties, required fields, etc.
    for key in ["properties", "required", "additionalProperties"]:
        if key in converted:
            schema[key] = converted[key]

    # Ensure standard k8s fields are present
    if "properties" not in schema:
        schema["properties"] = {}

    # Add apiVersion and kind if not present
    if "apiVersion" not in schema["properties"]:
        schema["properties"]["apiVersion"] = {
            "type": "string",
            "description": "APIVersion defines the versioned schema of this representation of an object.",
            "enum": [f"{group}/{version}"],
        }

    if "kind" not in schema["properties"]:
        schema["properties"]["kind"] = {
            "type": "string",
            "description": "Kind is a string value representing the REST resource this object represents.",
            "enum": [kind],
        }

    return schema


def deep_convert_schema(obj: Any) -> Any:
    """Recursively convert OpenAPI schema to JSON Schema.

    Handles Kubernetes-specific OpenAPI extensions:
    - x-kubernetes-int-or-string: Converts to anyOf[integer, string]
    - x-kubernetes-preserve-unknown-fields: Sets additionalProperties: true
    - nullable: Converts type to union with null
    """
    if not isinstance(obj, dict):
        return obj

    result = {}

    # Check for x-kubernetes-int-or-string before processing
    if obj.get("x-kubernetes-int-or-string"):
        # This field can be either an integer or a string
        result["anyOf"] = [{"type": "integer"}, {"type": "string"}]
        # Copy description if present
        if "description" in obj:
            result["description"] = obj["description"]
        return result

    # Check for x-kubernetes-preserve-unknown-fields
    if obj.get("x-kubernetes-preserve-unknown-fields"):
        result["additionalProperties"] = True

    # Track if nullable for later processing
    is_nullable = obj.get("nullable", False)

    for key, value in obj.items():
        # Skip OpenAPI-specific fields not in JSON Schema
        if key in [
            "x-kubernetes-preserve-unknown-fields",
            "x-kubernetes-int-or-string",
            "x-kubernetes-embedded-resource",
            "x-kubernetes-list-map-keys",
            "x-kubernetes-list-type",
            "x-kubernetes-map-type",
            "x-kubernetes-group-version-kind",
            "x-kubernetes-validations",
            "nullable",  # Handled separately below
        ]:
            continue

        # Recursively convert nested objects
        if isinstance(value, dict):
            result[key] = deep_convert_schema(value)
        elif isinstance(value, list):
            result[key] = [deep_convert_schema(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value

    # Handle nullable by converting type to array including null
    if is_nullable and "type" in result:
        current_type = result["type"]
        if isinstance(current_type, list):
            if "null" not in current_type:
                result["type"] = current_type + ["null"]
        else:
            result["type"] = [current_type, "null"]

    return result


# =============================================================================
# SCHEMA I/O
# =============================================================================


def parse_schema_path(schema_path: Path, base_dir: Path) -> tuple[str, str, str] | None:
    """Parse a schema file path to extract group, version, kind.

    Expected path structure: {base_dir}/{group}/{version}/{kind}.json

    Returns:
        Tuple of (group, version, kind) or None if path doesn't match expected structure.
    """
    try:
        rel_path = schema_path.relative_to(base_dir)
        parts = rel_path.parts

        if len(parts) != 3:
            return None

        group, version, kind_file = parts
        kind = kind_file.replace(".json", "")
        return (group, version, kind)
    except ValueError:
        return None


def load_schema(path: Path) -> dict:
    """Load a JSON schema from disk."""
    with open(path) as f:
        return json.load(f)


def save_schema(path: Path, schema: dict):
    """Save a JSON schema to disk."""
    with open(path, "w") as f:
        json.dump(schema, f, indent=2)


def write_schema(output_dir: Path, group: str, version: str, kind: str, schema: dict):
    """Write a JSON schema to the output directory structure."""
    # Create directory structure: {group}/{version}/{kind}.json
    schema_dir = output_dir / group / version
    schema_dir.mkdir(parents=True, exist_ok=True)

    schema_path = schema_dir / f"{kind}.json"
    save_schema(schema_path, schema)

    logger.debug("Wrote: %s", schema_path)


def compute_schema_hash(schema: dict) -> str:
    """
    Compute a content hash for a schema, ignoring metadata fields.

    This allows comparing schemas from different sources to detect duplicates.
    """
    # Create a copy without metadata fields that vary between extractions
    schema_copy = schema.copy()
    schema_copy.pop("x-kubernetes-schema-metadata", None)
    schema_copy.pop("$id", None)

    # Stable JSON serialization
    content = json.dumps(schema_copy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()[:16]
