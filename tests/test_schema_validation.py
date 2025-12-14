"""
Tests for JSON Schema validation of sources.yaml.
"""

import json
import sys
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestSourcesSchemaValidation:
    """Tests for sources.yaml schema validation."""

    @pytest.fixture
    def schema(self):
        """Load the sources schema."""
        schema_path = Path(__file__).parent.parent / "schemas" / "sources.schema.json"
        with open(schema_path) as f:
            return json.load(f)

    @pytest.fixture
    def validator(self, schema):
        """Create a JSON Schema validator."""
        jsonschema = pytest.importorskip("jsonschema")
        return jsonschema.Draft202012Validator(schema)

    def test_valid_helm_source(self, validator):
        """Test that a valid helm source passes validation."""
        config = {
            "sources": [
                {
                    "name": "test-chart",
                    "type": "helm",
                    "registry": "https://charts.example.io",
                    "chart": "my-chart",
                    "version": "1.0.0",
                }
            ]
        }

        errors = list(validator.iter_errors(config))
        assert len(errors) == 0

    def test_valid_helm_source_with_values(self, validator):
        """Test helm source with optional values."""
        config = {
            "sources": [
                {
                    "name": "test-chart",
                    "type": "helm",
                    "registry": "oci://ghcr.io/example",
                    "chart": "my-chart",
                    "version": "1.0.0",
                    "values": {"crds": {"enabled": True}},
                }
            ]
        }

        errors = list(validator.iter_errors(config))
        assert len(errors) == 0

    def test_valid_github_source_with_crd_path(self, validator):
        """Test valid github source with crd_path."""
        config = {
            "sources": [
                {
                    "name": "test-repo",
                    "type": "github",
                    "repo": "owner/repo",
                    "version": "v1.0.0",
                    "crd_path": "config/crds",
                }
            ]
        }

        errors = list(validator.iter_errors(config))
        assert len(errors) == 0

    def test_valid_github_source_with_assets(self, validator):
        """Test valid github source with assets list."""
        config = {
            "sources": [
                {
                    "name": "test-repo",
                    "type": "github",
                    "repo": "owner/repo",
                    "version": "v1.0.0",
                    "assets": ["crds/crd1.yaml", "crds/crd2.yaml"],
                }
            ]
        }

        errors = list(validator.iter_errors(config))
        assert len(errors) == 0

    def test_valid_url_source(self, validator):
        """Test valid URL source."""
        config = {
            "sources": [
                {
                    "name": "test-url",
                    "type": "url",
                    "url": "https://example.com/crds/{version}/crd.yaml",
                    "version": "1.0.0",
                }
            ]
        }

        errors = list(validator.iter_errors(config))
        assert len(errors) == 0

    def test_invalid_missing_required_field(self, validator):
        """Test that missing required field fails validation."""
        config = {
            "sources": [
                {
                    "name": "test-chart",
                    "type": "helm",
                    "registry": "https://charts.example.io",
                    # Missing: chart, version
                }
            ]
        }

        errors = list(validator.iter_errors(config))
        assert len(errors) > 0

    def test_invalid_source_type(self, validator):
        """Test that invalid source type fails validation."""
        config = {"sources": [{"name": "test", "type": "invalid", "version": "1.0.0"}]}

        errors = list(validator.iter_errors(config))
        assert len(errors) > 0

    def test_invalid_name_pattern(self, validator):
        """Test that invalid name pattern fails validation."""
        config = {
            "sources": [
                {
                    "name": "Invalid_Name",  # Should be lowercase with hyphens
                    "type": "helm",
                    "registry": "https://charts.example.io",
                    "chart": "test",
                    "version": "1.0.0",
                }
            ]
        }

        errors = list(validator.iter_errors(config))
        assert len(errors) > 0

    def test_actual_sources_yaml_is_valid(self, validator):
        """Test that the actual sources.yaml file is valid."""
        import yaml

        sources_path = Path(__file__).parent.parent / "sources.yaml"
        with open(sources_path) as f:
            config = yaml.safe_load(f)

        errors = list(validator.iter_errors(config))

        # Print errors for debugging if any
        for error in errors:
            print(f"Validation error: {error.message}")
            print(f"  Path: {list(error.absolute_path)}")

        assert len(errors) == 0, f"sources.yaml has {len(errors)} validation errors"
