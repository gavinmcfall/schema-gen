---
description: Coding standards, naming conventions, and project guidelines
tags: ["CodingStandards", "Naming", "CommitGuidelines", "PythonStyle"]
audience: ["LLMs", "Humans"]
---

# Conventions

## Python Style

### General

- Python 3.12+
- Type hints for function parameters and returns
- Docstrings for public functions
- `pathlib.Path` for file paths (not string manipulation)

### Imports

```python
# Standard library first
import json
from pathlib import Path

# Third-party second
import requests
import yaml

# Local imports last
from common import crd_to_jsonschema, write_schema
```

### Function Style

```python
def extract_crds(source: dict, output_dir: Path) -> list[tuple[str, str, str, dict]]:
    """Extract CRDs from a source definition.

    Args:
        source: Source configuration from sources.yaml
        output_dir: Directory to write schemas

    Returns:
        List of (group, version, kind, schema) tuples
    """
    ...
```

---

## Naming Conventions

### Files

| Type | Pattern | Example |
|------|---------|---------|
| Python script | `snake_case.py` | `extract.py`, `generate_index.py` |
| YAML config | `lowercase.yaml` | `sources.yaml` |
| JSON schema | `lowercase.json` | `gitrepository.json` |

### Sources

| Field | Convention | Example |
|-------|------------|---------|
| name | lowercase, hyphenated | `cert-manager`, `external-secrets` |
| version | Include `v` prefix if upstream uses it | `v1.2.0`, `2.14.1` |

### Schemas

| Component | Convention | Example |
|-----------|------------|---------|
| API group | As-is from CRD | `source.toolkit.fluxcd.io` |
| Version | As-is from CRD | `v1`, `v1beta1` |
| Kind | Lowercase | `gitrepository` (not `GitRepository`) |

---

## Source Definition Format

### Required Fields

```yaml
- name: example          # Unique identifier (required)
  type: helm|github|url  # Source type (required)
  version: "1.0.0"       # Version to extract (required)
```

### Type-Specific Fields

**Helm**:
```yaml
- name: example
  type: helm
  repo: https://charts.example.com  # Helm repo URL
  chart: example                     # Chart name
  version: "1.0.0"
```

**GitHub**:
```yaml
- name: example
  type: github
  repo: owner/repo                   # GitHub repo
  version: v1.0.0
  asset: install.yaml                # Release asset (option 1)
  # OR
  crd_path: config/crd/bases         # Repo path (option 2)
```

**URL**:
```yaml
- name: example
  type: url
  url: https://example.com/{version}/crds.yaml  # {version} is substituted
  version: v1.0.0
```

---

## Git Conventions

### Commit Messages

**Format**: `type(scope): description`

| Type | Use For |
|------|---------|
| `feat` | New source or feature |
| `fix` | Bug fix |
| `chore` | Maintenance, version updates |
| `docs` | Documentation |
| `test` | Test additions or fixes |
| `refactor` | Code restructure |

**Examples**:
```
feat(sources): add keda operator CRDs
fix(extract): handle missing asset gracefully
chore(sources): update flux to 2.15.0
docs(readme): add installation instructions
test(common): add URL extraction tests
```

### Branch Strategy

- `main` is the deployment branch
- Direct commits to `main` for simple changes
- Feature branches for complex changes

---

## Testing Conventions

### Test Organization

```
tests/
├── conftest.py          # Shared fixtures
├── test_common.py       # Unit tests for common.py
└── test_extract.py      # Integration tests
```

### Fixture Naming

```python
@pytest.fixture
def sample_crd_v1():
    """Sample v1 CRD for testing conversion."""
    ...

@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory for test outputs."""
    ...
```

### Test Naming

```python
class TestSchemaConversion:
    def test_crd_to_jsonschema_v1(self):
        """Test converting v1 CRD to JSON schemas."""
        ...

    def test_schema_has_provenance_metadata(self):
        """Test that converted schema includes provenance."""
        ...
```

---

## Error Handling

### Extraction Errors

```python
# Log and continue for individual source failures
try:
    schemas = extract_source(source)
except Exception as e:
    print(f"Error extracting {source['name']}: {e}")
    continue  # Don't fail the whole run
```

### Network Errors

```python
# Retry with backoff for transient failures
response = requests.get(url, timeout=30)
response.raise_for_status()
```

---

## Common Patterns

### Processing Multi-Document YAML

```python
for doc in yaml.safe_load_all(content):
    if doc is None:
        continue
    if doc.get("kind") == "CustomResourceDefinition":
        crds.append(doc)
```

### Writing Schemas

```python
def write_schema(output_dir: Path, group: str, version: str, kind: str, schema: dict):
    """Write schema to correct path structure."""
    path = output_dir / group / version / f"{kind}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(schema, f, indent=2)
```

---

## Don'ts

- **Don't** hardcode versions in scripts (use sources.yaml)
- **Don't** commit schemas without provenance metadata
- **Don't** use `os.path` when `pathlib` works
- **Don't** catch generic `Exception` without logging
- **Don't** skip tests for new extraction logic
