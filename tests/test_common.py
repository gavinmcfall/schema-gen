"""
Tests for scripts/common.py shared utilities.
"""

import sys
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from common import (
    compute_schema_hash,
    convert_openapi_to_jsonschema,
    crd_to_jsonschema,
    load_schema,
    parse_crds_from_files,
    save_schema,
    write_schema,
)

from extract import (
    get_source_by_name,
    load_sources,
)


class TestSourceLoading:
    """Tests for source directory loading."""

    def test_load_sources_from_directory(self, sample_sources_dir):
        """Test loading sources from directory structure."""
        sources = load_sources(sample_sources_dir)

        # Should find all 4 sources (helm, kustomize, github, url)
        assert len(sources) == 4

    def test_load_sources_includes_helm(self, sample_sources_dir):
        """Test that helm sources are loaded correctly."""
        sources = load_sources(sample_sources_dir)
        source = get_source_by_name(sources, "test-helm")

        assert source is not None
        assert source["type"] == "helm"
        assert source["registry"] == "https://charts.example.io"
        assert source["chart"] == "test-chart"
        assert source["version"] == "1.0.0"

    def test_load_sources_includes_kustomize(self, sample_sources_dir):
        """Test that kustomize sources are loaded correctly."""
        sources = load_sources(sample_sources_dir)
        source = get_source_by_name(sources, "test-kustomize")

        assert source is not None
        assert source["type"] == "github"
        assert source["repo"] == "example/test-repo"
        assert source["crd_path"] == "config/crds"
        assert source["version"] == "v1.0.0"

    def test_load_sources_includes_github(self, sample_sources_dir):
        """Test that github sources are loaded correctly."""
        sources = load_sources(sample_sources_dir)
        source = get_source_by_name(sources, "test-github-assets")

        assert source is not None
        assert source["type"] == "github"
        assert source["repo"] == "example/test-repo"
        assert "assets" in source
        assert len(source["assets"]) == 2

    def test_load_sources_includes_url(self, sample_sources_dir):
        """Test that url sources are loaded correctly."""
        sources = load_sources(sample_sources_dir)
        source = get_source_by_name(sources, "test-url")

        assert source is not None
        assert source["type"] == "url"
        assert "{version}" in source["url"]

    def test_get_source_by_name_not_found(self, sample_sources_dir):
        """Test searching for non-existent source."""
        sources = load_sources(sample_sources_dir)
        source = get_source_by_name(sources, "non-existent")

        assert source is None


class TestCRDParsing:
    """Tests for CRD parsing from YAML files."""

    def test_parse_single_crd(self, sample_crd_file):
        """Test parsing a single CRD from file."""
        crds = parse_crds_from_files([sample_crd_file])

        assert len(crds) == 1
        assert crds[0]["kind"] == "CustomResourceDefinition"
        assert crds[0]["spec"]["names"]["kind"] == "Widget"

    def test_parse_multi_document_yaml(self, sample_multi_crd_file):
        """Test parsing multiple CRDs from multi-document YAML."""
        crds = parse_crds_from_files([sample_multi_crd_file])

        assert len(crds) == 2
        kinds = {crd["spec"]["names"]["kind"] for crd in crds}
        assert kinds == {"Widget", "Gadget"}

    def test_parse_skips_non_crd(self, temp_dir):
        """Test that non-CRD documents are skipped."""
        non_crd_file = temp_dir / "configmap.yaml"
        non_crd_file.write_text("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: test
data:
  key: value
""")
        crds = parse_crds_from_files([non_crd_file])

        assert len(crds) == 0

    def test_parse_empty_file(self, temp_dir):
        """Test parsing an empty file."""
        empty_file = temp_dir / "empty.yaml"
        empty_file.write_text("")

        crds = parse_crds_from_files([empty_file])
        assert len(crds) == 0


class TestSchemaConversion:
    """Tests for CRD to JSON Schema conversion."""

    def test_crd_to_jsonschema_v1(self, sample_crd_v1):
        """Test converting v1 CRD to JSON schemas."""
        schemas = crd_to_jsonschema(sample_crd_v1, "test-source", "1.0.0")

        # Should produce schemas for both versions (v1 and v1beta1)
        assert len(schemas) == 2

        # Check structure of returned tuples
        for group, version, kind, schema in schemas:
            assert group == "example.io"
            assert version in ["v1", "v1beta1"]
            assert kind == "widget"
            assert "$schema" in schema
            assert schema["title"] == "Widget"

    def test_crd_to_jsonschema_v1beta1(self, sample_crd_v1beta1):
        """Test converting v1beta1 CRD to JSON schema."""
        schemas = crd_to_jsonschema(sample_crd_v1beta1, "test-source", "1.0.0")

        assert len(schemas) == 1
        group, version, kind, schema = schemas[0]

        assert group == "example.io"
        assert version == "v1"
        assert kind == "gadget"

    def test_schema_has_provenance_metadata(self, sample_crd_v1):
        """Test that converted schema includes provenance metadata."""
        schemas = crd_to_jsonschema(sample_crd_v1, "test-source", "1.0.0")

        _, _, _, schema = schemas[0]

        assert "x-kubernetes-schema-metadata" in schema
        metadata = schema["x-kubernetes-schema-metadata"]
        assert metadata["sourceName"] == "test-source"
        assert metadata["sourceVersion"] == "1.0.0"
        assert "extractedAt" in metadata
        assert metadata["generator"] == "k8s-schemas.io"

    def test_schema_has_correct_id(self, sample_crd_v1):
        """Test that schema $id is correctly formatted."""
        schemas = crd_to_jsonschema(sample_crd_v1)

        _, _, _, schema = schemas[0]

        assert schema["$id"] == "https://k8s-schemas.io/example.io/v1/widget.json"

    def test_schema_includes_apiversion_kind(self, sample_crd_v1):
        """Test that apiVersion and kind are in schema properties."""
        schemas = crd_to_jsonschema(sample_crd_v1)

        _, _, _, schema = schemas[0]

        assert "apiVersion" in schema["properties"]
        assert "kind" in schema["properties"]

    def test_convert_openapi_strips_k8s_extensions(self):
        """Test that Kubernetes-specific extensions are stripped."""
        openapi_schema = {
            "type": "object",
            "x-kubernetes-preserve-unknown-fields": True,
            "x-kubernetes-validations": [{"rule": "test"}],
            "properties": {"field": {"type": "string", "x-kubernetes-int-or-string": True}},
        }

        schema = convert_openapi_to_jsonschema(openapi_schema, "test.io", "v1", "Test")

        # Extensions should be stripped
        assert "x-kubernetes-preserve-unknown-fields" not in schema
        assert "x-kubernetes-validations" not in schema
        assert "x-kubernetes-int-or-string" not in schema["properties"]["field"]


class TestSchemaIO:
    """Tests for schema file I/O operations."""

    def test_save_and_load_schema(self, temp_dir):
        """Test saving and loading a schema."""
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"test": {"type": "string"}},
        }

        schema_path = temp_dir / "test.json"
        save_schema(schema_path, schema)

        loaded = load_schema(schema_path)
        assert loaded == schema

    def test_write_schema_creates_directories(self, temp_dir):
        """Test that write_schema creates necessary directories."""
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema"}

        write_schema(temp_dir, "example.io", "v1", "widget", schema)

        expected_path = temp_dir / "example.io" / "v1" / "widget.json"
        assert expected_path.exists()

        loaded = load_schema(expected_path)
        assert loaded == schema


class TestSchemaHash:
    """Tests for schema content hashing."""

    def test_hash_ignores_metadata(self):
        """Test that hash ignores provenance metadata."""
        schema1 = {
            "type": "object",
            "x-kubernetes-schema-metadata": {"sourceName": "source1", "extractedAt": "2024-01-01T00:00:00Z"},
        }
        schema2 = {
            "type": "object",
            "x-kubernetes-schema-metadata": {"sourceName": "source2", "extractedAt": "2024-12-31T23:59:59Z"},
        }

        assert compute_schema_hash(schema1) == compute_schema_hash(schema2)

    def test_hash_ignores_id(self):
        """Test that hash ignores $id field."""
        schema1 = {"type": "object", "$id": "https://example.com/1"}
        schema2 = {"type": "object", "$id": "https://example.com/2"}

        assert compute_schema_hash(schema1) == compute_schema_hash(schema2)

    def test_hash_differs_for_different_content(self):
        """Test that different schemas produce different hashes."""
        schema1 = {"type": "object", "properties": {"a": {"type": "string"}}}
        schema2 = {"type": "object", "properties": {"b": {"type": "integer"}}}

        assert compute_schema_hash(schema1) != compute_schema_hash(schema2)

    def test_hash_is_deterministic(self):
        """Test that hash is deterministic for same content."""
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}

        hash1 = compute_schema_hash(schema)
        hash2 = compute_schema_hash(schema)

        assert hash1 == hash2
