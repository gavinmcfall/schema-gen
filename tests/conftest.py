"""
Pytest fixtures for schema-gen tests.
"""

import tempfile
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_crd_v1():
    """Sample CRD in v1 format (current standard)."""
    return {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "widgets.example.io"},
        "spec": {
            "group": "example.io",
            "names": {"kind": "Widget", "plural": "widgets", "singular": "widget"},
            "scope": "Namespaced",
            "versions": [
                {
                    "name": "v1",
                    "served": True,
                    "storage": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "properties": {
                                "apiVersion": {"type": "string"},
                                "kind": {"type": "string"},
                                "metadata": {"type": "object"},
                                "spec": {
                                    "type": "object",
                                    "properties": {
                                        "size": {"type": "integer", "minimum": 1, "maximum": 100},
                                        "color": {"type": "string", "enum": ["red", "green", "blue"]},
                                    },
                                    "required": ["size"],
                                },
                            },
                        }
                    },
                },
                {
                    "name": "v1beta1",
                    "served": True,
                    "storage": False,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "properties": {"spec": {"type": "object", "properties": {"size": {"type": "integer"}}}},
                        }
                    },
                },
            ],
        },
    }


@pytest.fixture
def sample_crd_v1beta1():
    """Sample CRD in v1beta1 format (legacy)."""
    return {
        "apiVersion": "apiextensions.k8s.io/v1beta1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "gadgets.example.io"},
        "spec": {
            "group": "example.io",
            "version": "v1",
            "names": {"kind": "Gadget", "plural": "gadgets"},
            "scope": "Namespaced",
            "validation": {
                "openAPIV3Schema": {
                    "type": "object",
                    "properties": {"spec": {"type": "object", "properties": {"replicas": {"type": "integer"}}}},
                }
            },
        },
    }


@pytest.fixture
def sample_crd_file(temp_dir, sample_crd_v1):
    """Write sample CRD to a file and return path."""
    crd_file = temp_dir / "widget-crd.yaml"
    crd_file.write_text(yaml.dump(sample_crd_v1))
    return crd_file


@pytest.fixture
def sample_multi_crd_file(temp_dir, sample_crd_v1, sample_crd_v1beta1):
    """Write multiple CRDs to a single file (multi-document YAML)."""
    crd_file = temp_dir / "crds.yaml"
    content = yaml.dump(sample_crd_v1) + "---\n" + yaml.dump(sample_crd_v1beta1)
    crd_file.write_text(content)
    return crd_file


@pytest.fixture
def sample_sources_dir(temp_dir):
    """Create sample sources directory structure."""
    sources_dir = temp_dir / "sources"

    # Helm source
    helm_dir = sources_dir / "helm" / "test-helm"
    helm_dir.mkdir(parents=True)
    (helm_dir / "helmrelease.yaml").write_text(yaml.dump({
        "repository": "https://charts.example.io",
        "chart": "test-chart",
        "version": "1.0.0",
    }))

    # Kustomize source (github with crd_path)
    kustomize_dir = sources_dir / "kustomize" / "test-kustomize"
    kustomize_dir.mkdir(parents=True)
    (kustomize_dir / "kustomization.yaml").write_text(yaml.dump({
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": ["https://github.com/example/test-repo//config/crds?ref=v1.0.0"],
    }))

    # GitHub source (with assets)
    github_dir = sources_dir / "github" / "test-github-assets"
    github_dir.mkdir(parents=True)
    with open(github_dir / "source.yaml", "w") as f:
        f.write("# renovate: datasource=github-releases depName=example/test-repo\n")
        yaml.dump({
            "repository": "example/test-repo",
            "version": "v1.0.0",
            "assets": ["crds/crd1.yaml", "crds/crd2.yaml"],
        }, f)

    # URL source
    url_dir = sources_dir / "url" / "test-url"
    url_dir.mkdir(parents=True)
    with open(url_dir / "source.yaml", "w") as f:
        f.write("# renovate: datasource=github-releases depName=example/test-repo\n")
        yaml.dump({
            "url": "https://example.com/releases/{version}/crds.yaml",
            "version": "v1.0.0",
        }, f)

    return sources_dir


# Legacy fixtures for backward compatibility with old tests
@pytest.fixture
def sample_sources_config():
    """Sample sources configuration (list format for direct use)."""
    return [
        {
            "name": "test-helm",
            "type": "helm",
            "registry": "https://charts.example.io",
            "chart": "test-chart",
            "version": "1.0.0",
        },
        {
            "name": "test-kustomize",
            "type": "github",
            "repo": "example/test-repo",
            "version": "v1.0.0",
            "crd_path": "config/crds",
        },
        {
            "name": "test-github-assets",
            "type": "github",
            "repo": "example/test-repo",
            "version": "v1.0.0",
            "assets": ["crds/crd1.yaml", "crds/crd2.yaml"],
        },
        {
            "name": "test-url",
            "type": "url",
            "url": "https://example.com/releases/{version}/crds.yaml",
            "version": "v1.0.0",
        },
    ]
