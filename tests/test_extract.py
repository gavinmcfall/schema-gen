"""
Tests for scripts/extract.py extraction functionality.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from extract import (
    discover_github_yaml_files,
    extract_github_crds,
    extract_source,
)


class TestExtractSource:
    """Tests for the main extract_source function."""

    def test_extract_source_unknown_type(self, temp_dir):
        """Test that unknown source type returns 0."""
        source = {"name": "test", "type": "unknown", "version": "1.0.0"}

        count = extract_source(source, temp_dir)
        assert count == 0


class TestGitHubExtraction:
    """Tests for GitHub-based CRD extraction."""

    @patch("extract.requests.get")
    def test_discover_github_yaml_files(self, mock_get):
        """Test discovering YAML files from GitHub directory."""
        # Mock GitHub API response
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "crd1.yaml", "path": "crds/crd1.yaml", "type": "file"},
                {"name": "crd2.yml", "path": "crds/crd2.yml", "type": "file"},
                {"name": "README.md", "path": "crds/README.md", "type": "file"},
                {"name": "subdir", "path": "crds/subdir", "type": "dir"},
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()

        # Mock the recursive call for subdir (empty)
        def side_effect(url, *args, **kwargs):
            response = MagicMock()
            response.raise_for_status = MagicMock()
            if "subdir" in url:
                response.json = lambda: [{"name": "crd3.yaml", "path": "crds/subdir/crd3.yaml", "type": "file"}]
            else:
                response.json = lambda: [
                    {"name": "crd1.yaml", "path": "crds/crd1.yaml", "type": "file"},
                    {"name": "crd2.yml", "path": "crds/crd2.yml", "type": "file"},
                    {"name": "README.md", "path": "crds/README.md", "type": "file"},
                    {"name": "subdir", "path": "crds/subdir", "type": "dir"},
                ]
            return response

        mock_get.side_effect = side_effect

        files = discover_github_yaml_files("owner/repo", "v1.0.0", "crds", {})

        # Should find yaml/yml files, skip README.md, recurse into subdir
        assert len(files) == 3
        assert "crds/crd1.yaml" in files
        assert "crds/crd2.yml" in files
        assert "crds/subdir/crd3.yaml" in files

    @patch("extract.requests.get")
    @patch("extract.discover_github_yaml_files")
    def test_extract_github_crds_with_crd_path(self, mock_discover, mock_get, temp_dir):
        """Test extracting CRDs using crd_path discovery."""
        # Mock discovery returning file paths
        mock_discover.return_value = ["crds/test.yaml"]

        # Mock fetching the actual file
        mock_response = MagicMock()
        mock_response.text = """
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: tests.example.io
spec:
  group: example.io
  names:
    kind: Test
    plural: tests
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
"""
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        source = {
            "name": "test-source",
            "type": "github",
            "repo": "example/repo",
            "version": "v1.0.0",
            "crd_path": "crds",
        }

        crd_files = extract_github_crds(source, temp_dir)

        assert len(crd_files) == 1
        assert crd_files[0].exists()

    @patch("extract.requests.get")
    def test_extract_github_crds_with_assets(self, mock_get, temp_dir):
        """Test extracting CRDs using explicit assets list."""
        mock_response = MagicMock()
        mock_response.text = """
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: tests.example.io
spec:
  group: example.io
  names:
    kind: Test
    plural: tests
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
"""
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        source = {
            "name": "test-source",
            "type": "github",
            "repo": "example/repo",
            "version": "v1.0.0",
            "assets": ["path/to/crd.yaml"],
        }

        crd_files = extract_github_crds(source, temp_dir)

        assert len(crd_files) == 1
        # Verify URL was constructed correctly
        mock_get.assert_called()
        call_url = mock_get.call_args[0][0]
        assert "raw.githubusercontent.com" in call_url
        assert "v1.0.0" in call_url


class TestEndToEndExtraction:
    """End-to-end extraction tests (require network, marked for optional running)."""

    @pytest.mark.integration
    def test_extract_real_github_source(self, temp_dir):
        """Test extracting from a real GitHub source (gateway-api)."""
        source = {
            "name": "gateway-api",
            "type": "github",
            "repo": "kubernetes-sigs/gateway-api",
            "version": "v1.2.1",
            "assets": ["config/crd/standard/gateway.networking.k8s.io_gateways.yaml"],
        }

        count = extract_source(source, temp_dir)

        # Should extract at least 1 schema
        assert count > 0

        # Verify files were created
        schema_files = list(temp_dir.rglob("*.json"))
        assert len(schema_files) > 0

    @pytest.mark.integration
    def test_extract_real_url_source(self, temp_dir):
        """Test extracting from a real URL source (hierarchical-namespaces)."""
        source = {
            "name": "hierarchical-namespaces",
            "type": "url",
            "url": "https://github.com/kubernetes-retired/hierarchical-namespaces/releases/download/{version}/default.yaml",
            "version": "v1.1.0",
        }

        count = extract_source(source, temp_dir)

        # HNC should have 4 CRDs
        assert count == 4

        # Verify files were created
        schema_files = list(temp_dir.rglob("*.json"))
        assert len(schema_files) == 4
